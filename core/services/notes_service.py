from __future__ import annotations

from dataclasses import dataclass

from core.repository import LectureRepository
from core.services.groq_client import GroqClient

NOTE_MODE_EXACT = "exact"
NOTE_MODE_REFORMULATED = "reformulated"


@dataclass(frozen=True)
class _DocExcerpt:
    filename: str
    text: str


class NotesService:
    def __init__(self, repository: LectureRepository, groq_client: GroqClient) -> None:
        self.repository = repository
        self.groq_client = groq_client

    def _build_documents_context(
        self,
        *,
        audio_id: int,
        max_total_chars: int = 9000,
        max_per_doc_chars: int = 2500,
    ) -> str:
        documents = self.repository.list_documents(audio_id=audio_id)
        if not documents:
            return ""

        excerpts: list[_DocExcerpt] = []
        remaining = max_total_chars
        for doc in documents:
            if remaining <= 0:
                break
            filename = str(doc.get("original_filename") or "Unknown")
            extracted = str(doc.get("extracted_text") or "").strip()
            if not extracted:
                continue
            take = min(max_per_doc_chars, remaining)
            snippet = extracted[:take].strip()
            if len(extracted) > take:
                snippet = f"{snippet}\n\n[...truncated...]"
            excerpts.append(_DocExcerpt(filename=filename, text=snippet))
            remaining -= len(snippet)

        if not excerpts:
            return ""

        parts = ["Supporting documents (excerpts):"]
        for ex in excerpts:
            parts.append(f"--- {ex.filename} ---\n{ex.text}")
        return "\n\n".join(parts).strip()

    def generate_notes(self, audio_id: int, mode: str) -> str:
        transcript = self.repository.get_transcript_by_audio(audio_id)
        if transcript is None:
            raise RuntimeError(
                "No transcript found for this audio. Transcribe the lecture on the Audio page first."
            )

        corrected_text = str(transcript.get("corrected_text", "")).strip()
        raw_text = str(transcript.get("raw_text", "")).strip()
        if corrected_text:
            source_text = corrected_text
        elif raw_text:
            source_text = raw_text
        else:
            raise RuntimeError("Transcript is empty.")

        if mode == NOTE_MODE_EXACT:
            style_instruction = (
                "Create structured study notes using wording as close as possible to the teacher's original phrasing. "
                "Use headings and bullet points."
            )
        else:
            style_instruction = (
                "Create structured study notes by reformulating concepts in clear student-friendly language. "
                "Keep key meaning accurate and use headings and bullet points."
            )

        system_prompt = (
            "You create concise, well-structured lecture notes in Markdown. "
            "Do not wrap the output in code fences."
        )
        documents_context = self._build_documents_context(audio_id=audio_id)
        user_prompt = (
            f"{style_instruction}\n\n"
            "Use both the transcript and any supporting documents (if provided). "
            "If a supporting document conflicts with the transcript, prefer the transcript.\n\n"
            "Transcript:\n"
            f"{source_text}"
            + (f"\n\n{documents_context}" if documents_context else "")
        )

        notes_text = self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )
        self.repository.add_note(audio_id=audio_id, mode=mode, content=notes_text)
        return notes_text
