from django.conf import settings
from django.db import models


class Course(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses"
    )
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title


class Lecture(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lectures")
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    primary_audio = models.ForeignKey(
        "Audio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_for_lectures",
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title


class Audio(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="audios"
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audios",
    )
    title = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=512)
    stored_path = models.CharField(max_length=1024)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title


class Transcript(models.Model):
    audio = models.OneToOneField(
        Audio, on_delete=models.CASCADE, related_name="transcript"
    )
    raw_text = models.TextField()
    corrected_text = models.TextField()
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Transcript for {self.audio_id}"


class Document(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents"
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    audio = models.ForeignKey(
        Audio, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )
    original_filename = models.CharField(max_length=512)
    stored_path = models.CharField(max_length=1024)
    extracted_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.original_filename


class Note(models.Model):
    audio = models.ForeignKey(Audio, on_delete=models.CASCADE, related_name="notes")
    mode = models.CharField(max_length=32)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Quiz(models.Model):
    audio = models.ForeignKey(Audio, on_delete=models.CASCADE, related_name="quizzes")
    num_questions = models.PositiveIntegerField()
    focus = models.CharField(max_length=255, null=True, blank=True)
    difficulty = models.CharField(max_length=64, null=True, blank=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Flashcard(models.Model):
    lecture = models.ForeignKey(
        Lecture, on_delete=models.CASCADE, related_name="flashcards"
    )
    front = models.TextField()
    back = models.TextField()
    order_index = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order_index", "id"]

    def __str__(self) -> str:
        return f"Flashcard {self.id}"
