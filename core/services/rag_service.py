from __future__ import annotations

import re
from dataclasses import dataclass

from core.repository import LectureRepository
from core.services.groq_client import GroqClient
from core.services.vector_store_service import VectorStoreService

MAX_CHARS = 900
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    source_label: str
    text: str
    source_kind: str


class RagService:
    def __init__(self, repository: LectureRepository, groq_client: GroqClient) -> None:
        self.repository = repository
        self.groq_client = groq_client
        self.vector_store = VectorStoreService()

    def _split_long_text(self, text: str, max_chars: int) -> list[str]:
        content = text.strip()
        if not content:
            return []
        if len(content) <= max_chars:
            return [content]

        units = [
            part.strip()
            for part in SENTENCE_SPLIT_PATTERN.split(content)
            if part.strip()
        ]
        if len(units) <= 1:
            units = [part.strip() for part in re.split(r"\n+", content) if part.strip()]

        if len(units) <= 1:
            return [
                content[i : i + max_chars].strip()
                for i in range(0, len(content), max_chars)
                if content[i : i + max_chars].strip()
            ]

        pieces: list[str] = []
        current = ""
        for unit in units:
            if len(unit) > max_chars:
                if current:
                    pieces.append(current)
                    current = ""
                words = unit.split()
                hard_chunk = ""
                for word in words:
                    candidate = f"{hard_chunk} {word}".strip()
                    if len(candidate) <= max_chars:
                        hard_chunk = candidate
                    else:
                        if hard_chunk:
                            pieces.append(hard_chunk)
                        hard_chunk = word
                if hard_chunk:
                    pieces.append(hard_chunk)
                continue

            candidate = f"{current} {unit}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = unit

        if current:
            pieces.append(current)
        return pieces

    def _chunk_text(self, text: str, max_chars: int = MAX_CHARS) -> list[str]:
        paragraphs = [
            part.strip() for part in re.split(r"\n{2,}", text) if part.strip()
        ]
        if not paragraphs:
            plain = text.strip()
            return [plain] if plain else []

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            paragraph_pieces = self._split_long_text(paragraph, max_chars=max_chars)
            for piece in paragraph_pieces:
                if len(current) + len(piece) + 2 <= max_chars:
                    current = f"{current}\n\n{piece}".strip()
                    continue
                if current:
                    chunks.append(current)
                current = piece
        if current:
            chunks.append(current)
        return chunks

    def _collect_all_chunks(self) -> list[tuple[str, str, str]]:
        chunks: list[tuple[str, str, str]] = []


        # Include transcripts (prefer corrected_text, fall back to raw_text)
        for audio in self.repository.list_audios_with_transcripts():
            audio_id = audio.get("id")
            title = audio.get("title") or f"Audio {audio_id}"
            transcript = self.repository.get_transcript_by_audio(audio_id)
            if not transcript:
                continue
            text = str(transcript.get("corrected_text") or transcript.get("raw_text") or "").strip()
            if not text:
                continue
            source_label = f"Transcript - {title}"
            for piece in self._chunk_text(text):
                chunks.append((piece, source_label, "transcript"))

        for document in self.repository.list_documents(audio_id=None):
            text = str(document.get('extracted_text') or "").strip()
            if not text:
                continue
            source_label = f"Document - {document.get('original_filename', 'Unknown')}"
            for piece in self._chunk_text(text):
                chunks.append((piece, source_label, "document"))

        return chunks

    def rebuild_index(self) -> None:
        self.vector_store.clear_collection()
        all_chunks = self._collect_all_chunks()
        if not all_chunks:
            return
        self.vector_store.add_chunks(
            [(text, source_label, kind) for text, source_label, kind in all_chunks]
        )

    def index_audio(self, audio_id: int) -> None:
        # Rebuild index if any transcript text exists (corrected or raw)
        transcript = self.repository.get_transcript_by_audio(audio_id)
        if not transcript:
            return
        text = str(transcript.get("corrected_text") or transcript.get("raw_text") or "").strip()
        if not text:
            return
        self.rebuild_index()

    def index_document(self, document_id: int) -> None:
        docs = self.repository.list_documents()
        if not any(d["id"] == document_id for d in docs):
            return
        self.rebuild_index()

    def delete_document_vectors(self, source_label: str) -> None:
        self.vector_store.delete_by_source(source_label)

    def retrieve_context(
        self, question: str, audio_id: int | None = None, top_k: int = 6
    ) -> list[Chunk]:
        raw_chunks = self.vector_store.similarity_search(
            question, top_k=top_k * 2 if audio_id else top_k
        )

        filtered = []
        for text, meta in raw_chunks:
            if audio_id is not None:
                chunk_audio_id = self._guess_audio_id_from_source(meta["source_label"])
                if chunk_audio_id != audio_id:
                    continue
            filtered.append((text, meta))
            if len(filtered) >= top_k:
                break

        return [
            Chunk(
                source_label=meta["source_label"],
                text=text,
                source_kind=meta["kind"],
            )
            for text, meta in filtered
        ]

    def _guess_audio_id_from_source(self, source_label: str) -> int | None:
        if source_label.startswith("Transcript - "):
            title = source_label[13:]
            for audio in self.repository.list_audios():
                if audio.get("title") == title:
                    return audio["id"]
            return None
        if source_label.startswith("Document - "):
            filename = source_label[11:]
            for doc in self.repository.list_documents():
                if doc.get("original_filename") == filename:
                    return doc.get("audio_id")
            return None
        return None

    def answer_question(
        self, question: str, audio_id: int | None = None
    ) -> dict[str, object]:
        question_text = question.strip()
        if not question_text:
            raise RuntimeError("Question is empty.")

        context_chunks = self.retrieve_context(
            question_text, audio_id=audio_id, top_k=6
        )
        if not context_chunks:
            raise RuntimeError("No relevant context found in the knowledge base.")

        context_sections = [
            f"[Source {idx}] {chunk.source_label}\n{chunk.text}"
            for idx, chunk in enumerate(context_chunks, start=1)
        ]
        context_block = "\n\n".join(context_sections)

        system_prompt = (
            "You are OmniScribe's study assistant. "
            "Answer strictly from the provided context. "
            "If context is insufficient, clearly say what is missing."
        )
        user_prompt = (
            "Use the following context to answer the question. Include source numbers when relevant.\n\n"
            f"{context_block}\n\n"
            f"Question: {question_text}"
        )

        answer = self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )

        unique_sources: list[str] = []
        seen: set[str] = set()
        for chunk in context_chunks:
            if chunk.source_label not in seen:
                seen.add(chunk.source_label)
                unique_sources.append(chunk.source_label)

        return {"answer": answer, "sources": unique_sources}
