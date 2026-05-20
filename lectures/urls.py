from django.urls import path

from lectures import views

app_name = "lectures"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("courses/<int:course_id>/", views.course_detail, name="course_detail"),
    path("audio/", views.audio_workspace, name="audio"),
    path("audio/<int:audio_id>/stream/", views.audio_stream, name="audio_stream"),
    path("documents/", views.document_workspace, name="documents"),
    path("notes/", views.notes_view, name="notes"),
    path("flashcards/", views.flashcards_view, name="flashcards"),
    path("quiz/", views.quiz_view, name="quiz"),
    path("chat/", views.chat_view, name="chat"),
    path("api/health/", views.api_health, name="api_health"),
    path("api/chat/", views.api_chat, name="api_chat"),
    # Legacy redirects
    path("audio/upload/", views.audio_workspace, name="audio_upload"),
    path("audio/list/", views.audio_workspace, name="audio_list"),
    path("documents/upload/", views.document_workspace, name="document_upload"),
    path("documents/list/", views.document_workspace, name="document_list"),
]
