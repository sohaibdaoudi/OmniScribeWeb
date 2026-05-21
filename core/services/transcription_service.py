from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable, Iterable

from django.conf import settings
from django.db import transaction

from core.repository import LectureRepository
from core.services.document_service import DocumentService
from core.services.groq_client import GroqClient
from core.services.rag_service import RagService
from core.storage import get_storage


class TranscriptionService:
    def __init__(
        self,
        repository: LectureRepository,
        groq_client: GroqClient,
        rag_service: RagService,
        document_service: DocumentService | None = None,
    ) -> None:
        self.repository = repository
        self.groq_client = groq_client
        self.rag_service = rag_service
        self.document_service = document_service
        self.storage = get_storage()

    def _upload_audio_file(self, source_audio_path: Path) -> str:
        return self.storage.upload_file(
            prefix=settings.MINIO_AUDIO_PREFIX,
            source_path=source_audio_path,
        )

    def _correct_transcript(self, raw_transcript: str) -> str:
        system_prompt = (
            "You are an academic transcription correction assistant. "
            "Fix grammar, punctuation, and obvious speech-to-text mistakes while preserving meaning."
        )
        user_prompt = (
            "Correct the following transcript. Return only the corrected transcript text.\n\n"
            f"{raw_transcript}"
        )
        return self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

    def correct_existing_transcript(self, audio_id: int) -> str:
        transcript = self.repository.get_transcript_by_audio(audio_id)
        if transcript is None:
            raise RuntimeError("Transcript not found for this lecture.")
        raw_text = str(transcript.get("raw_text", "")).strip()
        if not raw_text:
            raise RuntimeError("Raw transcript is empty.")
        corrected = self._correct_transcript(raw_text)
        self.repository.save_transcript(audio_id, raw_text, corrected)
        self.rag_service.index_audio(audio_id)
        return corrected

    @transaction.atomic
    def process_audio(
        self,
        source_audio_path: str | Path,
        title: str | None = None,
        document_paths: Iterable[str | Path] | None = None,
        lecture_id: int | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> int:
        """Full desktop pipeline: audio → transcribe → save → docs → RAG index (no auto-correction)."""
        source_path = Path(source_audio_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {source_path}")

        if progress_callback:
            progress_callback("uploading")
        object_key = self._upload_audio_file(source_path)

        audio_title = title.strip() if title and title.strip() else source_path.stem
        audio_id = self.repository.add_audio(
            title=audio_title,
            original_filename=source_path.name,
            stored_path=object_key,
            lecture_id=lecture_id,
        )

        local_path = self.storage.get_local_copy(object_key, suffix=source_path.suffix)
        try:
            if progress_callback:
                progress_callback("transcribing")
            raw_transcript = self.groq_client.transcribe_audio(local_path)

            # Save raw transcript without auto-correction.
            # Corrected text stays empty until user explicitly corrects.
            self.repository.save_transcript(audio_id, raw_transcript, "")

            if document_paths and self.document_service:
                if progress_callback:
                    progress_callback("documents")
                for doc_path in document_paths:
                    self.document_service.store_document(
                        Path(doc_path),
                        audio_id=audio_id,
                        lecture_id=lecture_id,
                        reindex=False,
                    )

            if progress_callback:
                progress_callback("indexing")
            self.rag_service.rebuild_index()

            return audio_id
        finally:
            if local_path.exists():
                local_path.unlink()

    def process_uploaded_file(
        self,
        uploaded_file,
        title: str | None = None,
        uploaded_documents: list | None = None,
        lecture_id: int | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> int:
        temp_dir = settings.OMNISCRIBE_TEMP_DIR
        temp_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(uploaded_file.name).suffix or ".audio"
        temp_path = temp_dir / f"{uuid.uuid4().hex}{suffix}"
        doc_temp_paths: list[Path] = []

        with temp_path.open("wb") as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)

        if uploaded_documents:
            for doc_file in uploaded_documents:
                doc_suffix = Path(doc_file.name).suffix or ".bin"
                doc_temp = temp_dir / f"{uuid.uuid4().hex}{doc_suffix}"
                with doc_temp.open("wb") as dest:
                    for chunk in doc_file.chunks():
                        dest.write(chunk)
                doc_temp_paths.append(doc_temp)

        try:
            return self.process_audio(
                temp_path,
                title=title,
                document_paths=doc_temp_paths,
                lecture_id=lecture_id,
                progress_callback=progress_callback,
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()
            for doc_temp in doc_temp_paths:
                if doc_temp.exists():
                    doc_temp.unlink()
