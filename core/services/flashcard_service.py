from __future__ import annotations

import json
import re
from dataclasses import dataclass

from core.repository import LectureRepository
from core.services.groq_client import GroqClient


@dataclass(frozen=True)
class _DocExcerpt:
    filename: str
    text: str


class FlashcardService:
    def __init__(self, repository: LectureRepository, groq_client: GroqClient) -> None:
        self.repository = repository
        self.groq_client = groq_client

    def _build_documents_context(
        self,
        *,
        lecture_id: int,
        max_total_chars: int = 9000,
        max_per_doc_chars: int = 2500,
    ) -> str:
        documents = [
            d
            for d in self.repository.list_documents()
            if d.get("lecture_id") == lecture_id
        ]
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

    def _extract_json(self, raw: str) -> str:
        trimmed = raw.strip()
        if trimmed.startswith("[") and trimmed.endswith("]"):
            return trimmed
        match = re.search(r"\[.*\]", trimmed, re.DOTALL)
        if not match:
            raise RuntimeError("Flashcard output did not include JSON.")
        return match.group(0)

    def generate_flashcards(
        self,
        *,
        lecture_id: int,
        count: int = 12,
        focus: str | None = None,
    ) -> list[dict[str, str]]:
        lecture = self.repository.get_lecture(lecture_id)
        if not lecture or not lecture.primary_audio_id:
            raise RuntimeError("Lecture does not have an audio transcript yet.")

        transcript = self.repository.get_transcript_by_audio(lecture.primary_audio_id)
        if transcript is None:
            raise RuntimeError(
                "No transcript found for this lecture. Transcribe the lecture first."
            )
        corrected_text = str(transcript.get("corrected_text", "")).strip()
        raw_text = str(transcript.get("raw_text", "")).strip()
        if corrected_text:
            source_text = corrected_text
        elif raw_text:
            source_text = raw_text
        else:
            raise RuntimeError("Transcript is empty.")

        n = max(1, min(40, int(count)))
        focus_text = (focus or "").strip()
        focus_clause = (
            f"Focus on: {focus_text}" if focus_text else "Focus: overall lecture"
        )

        system_prompt = (
            "You create concise study flashcards. "
            "Return only valid JSON with no code fences or commentary."
        )
        documents_context = self._build_documents_context(lecture_id=lecture_id)
        user_prompt = (
            f"Create {n} flashcards from the lecture content.\n"
            f"{focus_clause}.\n\n"
            "Return JSON ONLY with this exact schema:\n"
            "[{\"front\": \"question\", \"back\": \"answer\"}, ...]\n\n"
            "Use short, clear wording. Do not invent facts.\n\n"
            "Lecture transcript:\n"
            f"{source_text}"
            + (f"\n\n{documents_context}" if documents_context else "")
        )

        raw = self.groq_client.chat_completion(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )
        json_text = self._extract_json(raw)
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Flashcard JSON could not be parsed.") from exc

        if not isinstance(data, list):
            raise RuntimeError("Flashcard JSON must be a list.")
        cards = []
        for item in data:
            if not isinstance(item, dict):
                continue
            front = str(item.get("front", "")).strip()
            back = str(item.get("back", "")).strip()
            if not front or not back:
                continue
            cards.append({"front": front, "back": back})

        if not cards:
            raise RuntimeError("No flashcards were generated.")

        self.repository.replace_flashcards(lecture_id, cards)
        return cards
