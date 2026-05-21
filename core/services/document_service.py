from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path

import fitz
import numpy as np
from django.conf import settings
from docx import Document
from PIL import Image
from pypdf import PdfReader

from core.repository import LectureRepository
from core.services.rag_service import RagService
from core.storage import get_storage

logger = logging.getLogger(__name__)

_OCR_READER = None


def get_ocr_reader():
    global _OCR_READER
    if _OCR_READER is None:
        import easyocr

        _OCR_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _OCR_READER


class DocumentService:
    def __init__(
        self,
        repository: LectureRepository,
        rag_service: RagService,
    ) -> None:
        self.repository = repository
        self.rag_service = rag_service
        self.storage = get_storage()

    def _upload_document(self, source_document_path: Path) -> str:
        return self.storage.upload_file(
            prefix=settings.MINIO_DOCUMENT_PREFIX,
            source_path=source_document_path,
        )

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        try:
            reader = PdfReader(str(pdf_path))
            parts = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(parts).strip()
        except Exception as e:
            logger.warning("PyPDF extraction failed for %s: %s", pdf_path, e)
            return ""

    def _extract_docx_text(self, docx_path: Path) -> str:
        document = Document(str(docx_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()

    def _ocr_image(self, image_path: Path) -> str:
        reader = get_ocr_reader()
        result = reader.readtext(str(image_path), detail=0, paragraph=True)
        return "\n".join(result).strip()

    def _ocr_pdf(self, pdf_path: Path, dpi: int = 150) -> str:
        reader = get_ocr_reader()
        all_text = []
        doc = fitz.open(pdf_path)
        try:
            for page_num in range(len(doc)):
                try:
                    pix = doc[page_num].get_pixmap(dpi=dpi)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    img_np = np.array(img)
                    result = reader.readtext(img_np, detail=0, paragraph=True)
                    page_text = "\n".join(result)
                    all_text.append(f"--- Page {page_num + 1} ---\n{page_text}")
                except Exception as e:
                    logger.warning(
                        "OCR failed for page %s of %s: %s", page_num + 1, pdf_path, e
                    )
                    all_text.append(f"--- Page {page_num + 1} ---\n[OCR error]")
        finally:
            doc.close()
        return "\n\n".join(all_text).strip()

    def _extract_text(self, source_document_path: Path) -> str:
        extension = source_document_path.suffix.lower()
        try:
            if extension == ".pdf":
                text = self._extract_pdf_text(source_document_path)
                if len(text) < 50:
                    logger.info("PDF seems scanned, falling back to OCR: %s", source_document_path)
                    text = self._ocr_pdf(source_document_path)
            elif extension in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
                text = self._ocr_image(source_document_path)
            elif extension == ".docx":
                text = self._extract_docx_text(source_document_path)
            else:
                text = source_document_path.read_text(
                    encoding="utf-8", errors="ignore"
                ).strip()
        except Exception as exc:
            logger.exception("Text extraction failed for %s", source_document_path)
            return f"Document uploaded but text extraction failed: {exc}"

        if not text:
            return "Document uploaded, but no readable text was extracted."
        return text

    def store_document(
        self,
        source_document_path: str | Path,
        audio_id: int | None = None,
        lecture_id: int | None = None,
        *,
        reindex: bool = True,
    ) -> int:
        source_path = Path(source_document_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Document file does not exist: {source_path}")

        extracted_text = self._extract_text(source_path)
        object_key = self._upload_document(source_path)

        document_id = self.repository.add_document(
            audio_id=audio_id,
            lecture_id=lecture_id,
            original_filename=source_path.name,
            stored_path=object_key,
            extracted_text=extracted_text,
        )
        if reindex:
            self.rag_service.index_document(document_id)
        return document_id

    def store_uploaded_files(
        self,
        uploaded_files: list,
        audio_id: int | None = None,
        lecture_id: int | None = None,
    ) -> list[int]:
        """Store multiple uploaded files and rebuild RAG index once (desktop parity)."""
        if not uploaded_files:
            return []

        document_ids: list[int] = []
        temp_paths: list[Path] = []
        temp_dir = settings.OMNISCRIBE_TEMP_DIR
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            for uploaded_file in uploaded_files:
                suffix = Path(uploaded_file.name).suffix or ".bin"
                temp_path = temp_dir / f"{uuid.uuid4().hex}{suffix}"
                with temp_path.open("wb") as dest:
                    for chunk in uploaded_file.chunks():
                        dest.write(chunk)
                temp_paths.append(temp_path)
                document_ids.append(
                    self.store_document(
                        temp_path,
                        audio_id=audio_id,
                        lecture_id=lecture_id,
                        reindex=False,
                    )
                )
            if document_ids:
                self.rag_service.rebuild_index()
            return document_ids
        finally:
            for temp_path in temp_paths:
                if temp_path.exists():
                    temp_path.unlink()

    def store_uploaded_file(
        self, uploaded_file, audio_id: int | None = None, lecture_id: int | None = None
    ) -> int:
        ids = self.store_uploaded_files(
            [uploaded_file], audio_id=audio_id, lecture_id=lecture_id
        )
        return ids[0]

    def _correct_document_text(self, extracted_text: str) -> str:
        system_prompt = (
            "You are an academic document clean-up assistant. "
            "Fix OCR noise, spelling, punctuation, and formatting while preserving meaning."
        )
        user_prompt = (
            "Clean and correct the following extracted text. Return only the corrected text.\n\n"
            f"{extracted_text}"
        )
        return self.rag_service.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

    def correct_documents_for_lecture(self, lecture_id: int) -> int:
        from lectures.models import Document as DocumentModel

        documents = DocumentModel.objects.filter(lecture_id=lecture_id)
        if not documents.exists():
            raise RuntimeError("No documents found for this lecture.")
        corrected_count = 0
        for doc in documents:
            extracted_text = str(doc.extracted_text or "").strip()
            if not extracted_text:
                continue
            corrected = self._correct_document_text(extracted_text)
            DocumentModel.objects.filter(id=doc.id).update(extracted_text=corrected)
            corrected_count += 1
        self.rag_service.rebuild_index()
        return corrected_count

    def delete_document(self, document_id: int) -> None:
        """Delete a document record, storage object, and related vectors."""
        from lectures.models import Document as DocumentModel

        doc = DocumentModel.objects.filter(id=document_id, user=self.repository.user).first()
        if not doc:
            raise ValueError("Document not found.")
        stored_path = doc.stored_path
        source_label = f"Document - {doc.original_filename}"

        try:
            self.storage.delete_object(stored_path)
        except Exception as exc:
            logger.exception("Storage cleanup failed for document %s", document_id)
            raise RuntimeError("Storage cleanup failed. Please try again.") from exc

        self.repository.delete_document(document_id)

        try:
            self.rag_service.delete_document_vectors(source_label)
        except Exception as exc:
            logger.warning("Vector cleanup failed, rebuilding index: %s", exc)
            try:
                self.rag_service.rebuild_index()
            except Exception as rebuild_exc:
                logger.warning(
                    "RAG rebuild failed after deleting document %s: %s",
                    document_id,
                    rebuild_exc,
                )
