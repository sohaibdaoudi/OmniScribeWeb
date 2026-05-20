from django.contrib import admin

from lectures.models import Audio, Document, Note, Quiz, Transcript


@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "created_at")
    search_fields = ("title", "original_filename")


@admin.register(Transcript)
class TranscriptAdmin(admin.ModelAdmin):
    list_display = ("id", "audio", "created_at")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "original_filename", "user", "audio", "created_at")


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("id", "audio", "mode", "created_at")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("id", "audio", "num_questions", "difficulty", "created_at")
