"""Django ORM repository mirroring desktop Database API."""
from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from django.db.models import Count, Exists, OuterRef, QuerySet, Q

from lectures.models import Audio, Course, Document, Flashcard, Lecture, Note, Quiz, Transcript


class LectureRepository:
    """User-scoped persistence layer compatible with desktop service contracts."""

    def __init__(self, user: User) -> None:
        self.user = user

    def _course_qs(self) -> QuerySet[Course]:
        return Course.objects.filter(user=self.user)

    def _lecture_qs(self) -> QuerySet[Lecture]:
        return Lecture.objects.filter(course__user=self.user)

    def _audio_qs(self) -> QuerySet[Audio]:
        return Audio.objects.filter(user=self.user)

    def _audios_with_transcript_qs(self) -> QuerySet[Audio]:
        return (
            self._audio_qs()
            .filter(transcript__isnull=False)
            .exclude(transcript__raw_text="")
            .select_related("transcript")
            .distinct()
        )

    def add_audio(
        self,
        title: str,
        original_filename: str,
        stored_path: str,
        lecture_id: int | None = None,
    ) -> int:
        lecture = None
        if lecture_id is not None:
            lecture = self.get_lecture(lecture_id)
            if lecture is None:
                raise ValueError(f"Lecture {lecture_id} not found")
        audio = Audio.objects.create(
            user=self.user,
            lecture=lecture,
            title=title,
            original_filename=original_filename,
            stored_path=stored_path,
        )
        if lecture and lecture.primary_audio_id is None:
            lecture.primary_audio = audio
            lecture.save(update_fields=["primary_audio"])
        return audio.id

    def delete_audio(self, audio_id: int) -> None:
        audio = self.get_audio(audio_id)
        if audio:
            audio.delete()

    def list_audios(self) -> list[dict[str, Any]]:
        transcript_exists = Transcript.objects.filter(
            audio_id=OuterRef("pk"),
            raw_text__gt="",
        )
        rows = []
        for audio in (
            self._audio_qs()
            .annotate(has_transcript=Exists(transcript_exists))
            .select_related("lecture__course")
            .order_by("-created_at", "-id")
        ):
            rows.append(
                {
                    "id": audio.id,
                    "lecture_id": audio.lecture_id,
                    "lecture_title": audio.lecture.title if audio.lecture else None,
                    "course_id": audio.lecture.course_id if audio.lecture else None,
                    "course_title": audio.lecture.course.title
                    if audio.lecture and audio.lecture.course
                    else None,
                    "title": audio.title,
                    "original_filename": audio.original_filename,
                    "stored_path": audio.stored_path,
                    "created_at": audio.created_at.isoformat(),
                    "has_transcript": bool(audio.has_transcript),
                }
            )
        return rows

    def list_audios_with_transcripts(self) -> list[dict[str, Any]]:
        rows = []
        for audio in (
            self._audios_with_transcript_qs()
            .select_related("lecture__course")
            .order_by("-created_at", "-id")
        ):
            rows.append(
                {
                    "id": audio.id,
                    "lecture_id": audio.lecture_id,
                    "lecture_title": audio.lecture.title if audio.lecture else None,
                    "course_id": audio.lecture.course_id if audio.lecture else None,
                    "course_title": audio.lecture.course.title
                    if audio.lecture and audio.lecture.course
                    else None,
                    "title": audio.title,
                    "original_filename": audio.original_filename,
                    "stored_path": audio.stored_path,
                    "created_at": audio.created_at.isoformat(),
                    "has_transcript": True,
                }
            )
        return rows

    def audio_has_transcript(self, audio_id: int) -> bool:
        return self._audios_with_transcript_qs().filter(id=audio_id).exists()

    def get_audio(self, audio_id: int) -> Audio | None:
        return self._audio_qs().filter(id=audio_id).first()

    def list_courses(self) -> list[dict[str, Any]]:
        rows = []
        for course in self._course_qs().annotate(lecture_count=Count("lectures")):
            rows.append(
                {
                    "id": course.id,
                    "title": course.title,
                    "lecture_count": course.lecture_count,
                    "created_at": course.created_at.isoformat(),
                }
            )
        return rows

    def get_course(self, course_id: int) -> Course | None:
        return self._course_qs().filter(id=course_id).first()

    def _normalize_course_title(self, title: str) -> str:
        """Normalize course title for deduplication."""
        return title.strip().lower()

    def _next_default_course_title(self) -> str:
        base = "Untitled course"
        titles = set(
            self._course_qs()
            .filter(title__startswith=base)
            .values_list("title", flat=True)
        )
        if base not in titles:
            return base
        suffixes: list[int] = []
        for title in titles:
            if title == base:
                continue
            if title.startswith(f"{base} "):
                maybe_num = title[len(base) + 1 :]
                if maybe_num.isdigit():
                    suffixes.append(int(maybe_num))
        next_num = max(suffixes, default=1) + 1
        return f"{base} {next_num}"

    def create_course(self, title: str | None = None) -> Course:
        final_title = (title or "").strip() or self._next_default_course_title()
        
        # Check if course with normalized title already exists
        normalized = self._normalize_course_title(final_title)
        for course in self._course_qs():
            if self._normalize_course_title(course.title) == normalized:
                return course
        
        return Course.objects.create(user=self.user, title=final_title)

    def rename_course(self, course_id: int, title: str) -> None:
        course = self.get_course(course_id)
        if not course:
            raise ValueError("Course not found.")
        clean = title.strip()
        if not clean:
            raise ValueError("Course title cannot be empty.")
        course.title = clean
        course.save(update_fields=["title"])

    def delete_course(self, course_id: int) -> None:
        course = self.get_course(course_id)
        if not course:
            raise ValueError("Course not found.")
        course.delete()

    def create_lecture(self, course_id: int, title: str) -> Lecture:
        course = self.get_course(course_id)
        if not course:
            raise ValueError("Course not found.")
        clean = title.strip()
        if not clean:
            raise ValueError("Lecture title cannot be empty.")
        return Lecture.objects.create(course=course, title=clean)

    def rename_lecture(self, lecture_id: int, title: str) -> None:
        lecture = self.get_lecture(lecture_id)
        if not lecture:
            raise ValueError("Lecture not found.")
        clean = title.strip()
        if not clean:
            raise ValueError("Lecture title cannot be empty.")
        lecture.title = clean
        lecture.save(update_fields=["title"])
        if lecture.primary_audio_id:
            Audio.objects.filter(id=lecture.primary_audio_id).update(title=clean)

    def delete_lecture(self, lecture_id: int) -> None:
        lecture = self.get_lecture(lecture_id)
        if not lecture:
            raise ValueError("Lecture not found.")
        lecture.delete()

    def get_lecture(self, lecture_id: int) -> Lecture | None:
        return (
            self._lecture_qs()
            .select_related("course", "primary_audio")
            .filter(id=lecture_id)
            .first()
        )

    def list_lectures(
        self, *, course_id: int | None = None, with_transcripts: bool = False
    ) -> list[dict[str, Any]]:
        qs = self._lecture_qs().select_related("course", "primary_audio")
        if course_id is not None:
            qs = qs.filter(course_id=course_id)
        if with_transcripts:
            transcript_exists = Transcript.objects.filter(
                audio_id=OuterRef("primary_audio_id"),
                raw_text__gt="",
            )
            qs = qs.annotate(has_transcript=Exists(transcript_exists))
        rows: list[dict[str, Any]] = []
        for lecture in qs.order_by("-created_at", "-id"):
            rows.append(
                {
                    "id": lecture.id,
                    "title": lecture.title,
                    "course_id": lecture.course_id,
                    "course_title": lecture.course.title if lecture.course else None,
                    "created_at": lecture.created_at.isoformat(),
                    "primary_audio_id": lecture.primary_audio_id,
                    "has_transcript": bool(getattr(lecture, "has_transcript", False)),
                }
            )
        return rows

    def get_dashboard_stats(self) -> dict[str, int]:
        return {
            "total_courses": self._course_qs().count(),
            "total_lectures": self._lecture_qs().count(),
            "total_audios": self._audio_qs().count(),
            "total_documents": Document.objects.filter(user=self.user).count(),
        }

    def save_transcript(self, audio_id: int, raw_text: str, corrected_text: str) -> None:
        audio = self.get_audio(audio_id)
        if not audio:
            raise ValueError(f"Audio {audio_id} not found")
        Transcript.objects.update_or_create(
            audio=audio,
            defaults={"raw_text": raw_text, "corrected_text": corrected_text},
        )

    def get_transcript_by_audio(self, audio_id: int) -> dict[str, Any] | None:
        transcript = (
            Transcript.objects.filter(audio__user=self.user, audio_id=audio_id)
            .select_related("audio")
            .first()
        )
        if not transcript:
            return None
        return {
            "id": transcript.id,
            "audio_id": transcript.audio_id,
            "raw_text": transcript.raw_text,
            "corrected_text": transcript.corrected_text,
            "created_at": transcript.created_at.isoformat(),
        }

    def add_document(
        self,
        original_filename: str,
        stored_path: str,
        extracted_text: str,
        audio_id: int | None = None,
        lecture_id: int | None = None,
    ) -> int:
        audio = None
        lecture = None
        if audio_id is not None:
            audio = self.get_audio(audio_id)
            if audio is None:
                raise ValueError(f"Audio {audio_id} not found for document link")
            if audio.lecture_id and lecture_id is None:
                lecture_id = audio.lecture_id
        if lecture_id is not None:
            lecture = self.get_lecture(lecture_id)
            if lecture is None:
                raise ValueError(f"Lecture {lecture_id} not found for document link")
        doc = Document.objects.create(
            user=self.user,
            lecture=lecture,
            audio=audio,
            original_filename=original_filename,
            stored_path=stored_path,
            extracted_text=extracted_text,
        )
        return doc.id

    def delete_document(self, document_id: int) -> None:
        from lectures.models import Document as DocumentModel

        doc = DocumentModel.objects.filter(id=document_id, user=self.user).first()
        if not doc:
            raise ValueError("Document not found.")
        doc.delete()

    def list_documents(
        self, audio_id: int | None = None, lecture_id: int | None = None
    ) -> list[dict[str, Any]]:
        qs = Document.objects.filter(user=self.user).select_related(
            "audio", "lecture", "lecture__course"
        )
        if audio_id is not None:
            audio = self.get_audio(audio_id)
            if audio and audio.lecture_id:
                qs = qs.filter(Q(audio_id=audio_id) | Q(lecture_id=audio.lecture_id))
            else:
                qs = qs.filter(audio_id=audio_id)
        if lecture_id is not None:
            qs = qs.filter(lecture_id=lecture_id)
        rows = []
        for doc in qs.order_by("-created_at", "-id"):
            rows.append(
                {
                    "id": doc.id,
                    "audio_id": doc.audio_id,
                    "lecture_id": doc.lecture_id,
                    "lecture_title": doc.lecture.title if doc.lecture else None,
                    "course_id": doc.lecture.course_id if doc.lecture else None,
                    "course_title": doc.lecture.course.title
                    if doc.lecture and doc.lecture.course
                    else None,
                    "original_filename": doc.original_filename,
                    "stored_path": doc.stored_path,
                    "extracted_text": doc.extracted_text,
                    "created_at": doc.created_at.isoformat(),
                    "audio_title": doc.audio.title if doc.audio else None,
                }
            )
        return rows

    def add_note(self, audio_id: int, mode: str, content: str) -> int:
        if not self.audio_has_transcript(audio_id):
            raise ValueError("No transcript available for this audio.")
        audio = self.get_audio(audio_id)
        if not audio:
            raise ValueError(f"Audio {audio_id} not found")
        note = Note.objects.create(audio=audio, mode=mode, content=content)
        return note.id

    def add_quiz(
        self,
        *,
        audio_id: int,
        num_questions: int,
        focus: str | None,
        difficulty: str | None,
        content: str,
    ) -> int:
        if not self.audio_has_transcript(audio_id):
            raise ValueError("No transcript available for this audio.")
        audio = self.get_audio(audio_id)
        if not audio:
            raise ValueError(f"Audio {audio_id} not found")
        quiz = Quiz.objects.create(
            audio=audio,
            num_questions=num_questions,
            focus=focus,
            difficulty=difficulty,
            content=content,
        )
        return quiz.id

    def get_latest_note(self, audio_id: int, mode: str | None = None) -> dict[str, Any] | None:
        qs = Note.objects.filter(audio__user=self.user, audio_id=audio_id)
        if mode is not None:
            qs = qs.filter(mode=mode)
        note = qs.order_by("-created_at", "-id").first()
        if not note:
            return None
        return {
            "id": note.id,
            "audio_id": note.audio_id,
            "mode": note.mode,
            "content": note.content,
            "created_at": note.created_at.isoformat(),
        }

    def get_latest_quiz(
        self,
        *,
        audio_id: int,
        difficulty: str | None = None,
        num_questions: int | None = None,
    ) -> dict[str, Any] | None:
        qs = Quiz.objects.filter(audio__user=self.user, audio_id=audio_id)
        if difficulty is not None:
            qs = qs.filter(difficulty=difficulty)
        if num_questions is not None:
            qs = qs.filter(num_questions=num_questions)
        quiz = qs.order_by("-created_at", "-id").first()
        if not quiz:
            return None
        return {
            "id": quiz.id,
            "audio_id": quiz.audio_id,
            "num_questions": quiz.num_questions,
            "focus": quiz.focus,
            "difficulty": quiz.difficulty,
            "content": quiz.content,
            "created_at": quiz.created_at.isoformat(),
        }

    def get_corrected_transcripts(self, audio_id: int | None = None) -> list[dict[str, Any]]:
        qs = Transcript.objects.filter(
            audio__user=self.user,
        ).exclude(corrected_text="").select_related("audio")
        if audio_id is not None:
            qs = qs.filter(audio_id=audio_id)
        rows = []
        for t in qs.order_by("-created_at", "-id"):
            rows.append(
                {
                    "id": t.id,
                    "audio_id": t.audio_id,
                    "corrected_text": t.corrected_text,
                    "created_at": t.created_at.isoformat(),
                    "audio_title": t.audio.title,
                }
            )
        return rows

    def get_audio_title(self, audio_id: int) -> str | None:
        audio = self.get_audio(audio_id)
        return audio.title if audio else None

    def replace_flashcards(self, lecture_id: int, cards: list[dict[str, str]]) -> int:
        lecture = self.get_lecture(lecture_id)
        if not lecture:
            raise ValueError("Lecture not found.")
        Flashcard.objects.filter(lecture=lecture).delete()
        created = []
        for idx, card in enumerate(cards, start=1):
            front = str(card.get("front", "")).strip()
            back = str(card.get("back", "")).strip()
            if not front or not back:
                continue
            created.append(
                Flashcard(
                    lecture=lecture,
                    front=front,
                    back=back,
                    order_index=idx,
                )
            )
        if created:
            Flashcard.objects.bulk_create(created)
        return len(created)

    def list_flashcards(self, lecture_id: int) -> list[dict[str, Any]]:
        lecture = self.get_lecture(lecture_id)
        if not lecture:
            return []
        return [
            {
                "id": card.id,
                "front": card.front,
                "back": card.back,
                "order_index": card.order_index,
            }
            for card in Flashcard.objects.filter(lecture=lecture).order_by(
                "order_index", "id"
            )
        ]
