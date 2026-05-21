"""Service factory — wires repository + services per authenticated user."""
from __future__ import annotations

from django.contrib.auth.models import User

from core.repository import LectureRepository
from core.services.api_status_service import ApiStatusService
from core.services.document_service import DocumentService
from core.services.flashcard_service import FlashcardService
from core.services.groq_client import GroqClient
from core.services.notes_service import NotesService
from core.services.quiz_service import QuizService
from core.services.rag_service import RagService
from core.services.transcription_service import TranscriptionService


class ServiceBundle:
    def __init__(self, user: User) -> None:
        self.repository = LectureRepository(user)
        self.groq_client = GroqClient.from_settings()
        self.api_status_service = ApiStatusService(self.groq_client)

        self._rag_service: RagService | None = None
        self._document_service: DocumentService | None = None
        self._transcription_service: TranscriptionService | None = None
        self._notes_service: NotesService | None = None
        self._quiz_service: QuizService | None = None
        self._flashcard_service: FlashcardService | None = None

    @property
    def rag_service(self) -> RagService:
        if self._rag_service is None:
            self._rag_service = RagService(self.repository, self.groq_client)
        return self._rag_service

    @property
    def document_service(self) -> DocumentService:
        if self._document_service is None:
            self._document_service = DocumentService(self.repository, self.rag_service)
        return self._document_service

    @property
    def transcription_service(self) -> TranscriptionService:
        if self._transcription_service is None:
            self._transcription_service = TranscriptionService(
                self.repository,
                self.groq_client,
                self.rag_service,
                document_service=self.document_service,
            )
        return self._transcription_service

    @property
    def notes_service(self) -> NotesService:
        if self._notes_service is None:
            self._notes_service = NotesService(self.repository, self.groq_client)
        return self._notes_service

    @property
    def quiz_service(self) -> QuizService:
        if self._quiz_service is None:
            self._quiz_service = QuizService(self.repository, self.groq_client)
        return self._quiz_service

    @property
    def flashcard_service(self) -> FlashcardService:
        if self._flashcard_service is None:
            self._flashcard_service = FlashcardService(self.repository, self.groq_client)
        return self._flashcard_service


def get_services(user: User) -> ServiceBundle:
    return ServiceBundle(user)
