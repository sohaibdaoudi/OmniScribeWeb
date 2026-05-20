from __future__ import annotations

import os
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.services.api_status_service import ApiStatusService
from core.services.factory import get_services
from core.services.groq_client import GroqClient
from core.services.notes_service import NOTE_MODE_EXACT, NOTE_MODE_REFORMULATED
from core.storage import get_storage
from lectures.models import Audio
from lectures.quiz_parser import parse_quiz_markdown


def _services(request: HttpRequest):
    return get_services(request.user)


def _parse_int(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@login_required
@require_http_methods(["GET", "POST"])
def dashboard(request: HttpRequest):
    # Extra safeguard: ensure unauthenticated users are redirected to login.
    from django.conf import settings

    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL)

    services = _services(request)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create_course":
            try:
                title = request.POST.get("title", "")
                services.repository.create_course(title)
                messages.success(request, "Course created.")
                return redirect("lectures:dashboard")
            except Exception as exc:
                messages.error(request, str(exc))
        elif action == "delete_course":
            course_id = _parse_int(request.POST.get("course_id", ""))
            if not course_id:
                messages.error(request, "Course not found.")
            else:
                try:
                    services.repository.delete_course(course_id)
                    messages.success(request, "Course deleted.")
                    return redirect("lectures:dashboard")
                except Exception as exc:
                    messages.error(request, str(exc))
        elif action == "rename_course":
            course_id = _parse_int(request.POST.get("course_id", ""))
            if not course_id:
                messages.error(request, "Course not found.")
            else:
                try:
                    services.repository.rename_course(course_id, request.POST.get("title", ""))
                    messages.success(request, "Course renamed.")
                    return redirect("lectures:dashboard")
                except Exception as exc:
                    messages.error(request, str(exc))

    return render(
        request,
        "lectures/dashboard.html",
        {
            "stats": services.repository.get_dashboard_stats(),
            "courses": services.repository.list_courses(),
            "lectures": services.repository.list_lectures(with_transcripts=True)[:8],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def audio_workspace(request: HttpRequest):
    """Audio page: Upload | Record | Transcripts (desktop parity)."""
    services = _services(request)
    tab = request.GET.get("tab", "upload")
    if tab not in ("upload", "record", "transcripts"):
        tab = "upload"

    selected_lecture_id = _parse_int(request.GET.get("lecture_id", ""))
    selected_audio_id = None
    transcript = None
    raw_transcript = None
    corrected_transcript = None

    if request.method == "POST":
        action = request.POST.get("action", "transcribe")
        if action == "transcribe":
            uploaded = request.FILES.get("audio_file")
            if not uploaded:
                messages.error(request, "Select an audio file first.")
                return redirect("lectures:audio")
            course_id = _parse_int(request.POST.get("course_id", ""))
            course_title = request.POST.get("course_title", "").strip() or None
            lecture_title = (
                request.POST.get("lecture_title", "").strip()
                or request.POST.get("title", "").strip()
                or None
            )
            doc_files = request.FILES.getlist("document_files")
            try:
                if course_id:
                    course = services.repository.get_course(course_id)
                    if not course:
                        messages.error(request, "Selected course not found.")
                        return redirect("lectures:audio")
                else:
                    course = services.repository.create_course(course_title)
                lecture = services.repository.create_lecture(
                    course.id, lecture_title or Path(uploaded.name).stem
                )
                audio_id = services.transcription_service.process_uploaded_file(
                    uploaded,
                    title=lecture.title,
                    uploaded_documents=doc_files,
                    lecture_id=lecture.id,
                )
                messages.success(
                    request,
                    "Lecture uploaded. Documents processed."
                    if doc_files
                    else "Lecture transcribed.",
                )
                return redirect(
                    f"{request.path}?tab=transcripts&lecture_id={lecture.id}"
                )
            except Exception as exc:
                messages.error(request, f"Transcription failed: {exc}")
        elif action == "transcribe_recording":
            uploaded = request.FILES.get("recorded_audio")
            if not uploaded:
                messages.error(request, "Record audio before transcribing.")
                return redirect(f"{request.path}?tab=record")
            course_id = _parse_int(request.POST.get("course_id", ""))
            course_title = request.POST.get("course_title", "").strip() or None
            lecture_title = request.POST.get("record_title", "").strip() or None
            try:
                if course_id:
                    course = services.repository.get_course(course_id)
                    if not course:
                        messages.error(request, "Selected course not found.")
                        return redirect(f"{request.path}?tab=record")
                else:
                    course = services.repository.create_course(course_title)
                lecture = services.repository.create_lecture(
                    course.id, lecture_title or "Recorded lecture"
                )
                audio_id = services.transcription_service.process_uploaded_file(
                    uploaded, title=lecture.title, lecture_id=lecture.id
                )
                messages.success(request, "Recording transcribed.")
                return redirect(
                    f"{request.path}?tab=transcripts&lecture_id={lecture.id}"
                )
            except Exception as exc:
                messages.error(request, f"Transcription failed: {exc}")
        elif action == "correct_transcript":
            lecture_id = _parse_int(request.POST.get("lecture_id", ""))
            if not lecture_id:
                messages.error(request, "Select a lecture first.")
            else:
                lecture = services.repository.get_lecture(lecture_id)
                if not lecture or not lecture.primary_audio_id:
                    messages.error(request, "Lecture transcript not found.")
                else:
                    try:
                        services.transcription_service.correct_existing_transcript(
                            lecture.primary_audio_id
                        )
                        messages.success(request, "Transcript corrected.")
                        return redirect(
                            f"{request.path}?tab=transcripts&lecture_id={lecture_id}"
                        )
                    except Exception as exc:
                        messages.error(request, f"Correction failed: {exc}")

    courses = services.repository.list_courses()
    lectures = services.repository.list_lectures()
    transcript_lectures = services.repository.list_lectures(with_transcripts=True)

    if selected_lecture_id:
        lecture = services.repository.get_lecture(selected_lecture_id)
        if lecture:
            selected_audio_id = lecture.primary_audio_id
        transcript = (
            services.repository.get_transcript_by_audio(selected_audio_id)
            if selected_audio_id
            else None
        )
        if transcript:
            raw_transcript = transcript.get("raw_text")
            corrected_transcript = transcript.get("corrected_text")
        tab = "transcripts"
    elif transcript_lectures:
        selected_lecture_id = transcript_lectures[0]["id"]
        selected_audio_id = transcript_lectures[0]["primary_audio_id"]
        transcript = services.repository.get_transcript_by_audio(selected_audio_id)
        if transcript:
            raw_transcript = transcript.get("raw_text")
            corrected_transcript = transcript.get("corrected_text")

    return render(
        request,
        "lectures/audio_workspace.html",
        {
            "tab": tab,
            "courses": courses,
            "lectures": lectures,
            "transcript_lectures": transcript_lectures,
            "selected_lecture_id": selected_lecture_id,
            "selected_audio_id": selected_audio_id,
            "raw_transcript": raw_transcript,
            "corrected_transcript": corrected_transcript,
            "linked_documents": services.repository.list_documents(
                lecture_id=selected_lecture_id
            )
            if selected_lecture_id
            else [],
        },
    )


@login_required
def audio_stream(request: HttpRequest, audio_id: int):
    audio = get_object_or_404(Audio, id=audio_id, user=request.user)
    storage = get_storage()
    temp_path = storage.get_local_copy(audio.stored_path)
    content_type = "audio/mpeg"
    ext = temp_path.suffix.lower()
    if ext == ".wav":
        content_type = "audio/wav"
    elif ext in (".m4a", ".aac"):
        content_type = "audio/mp4"
    elif ext == ".ogg":
        content_type = "audio/ogg"
    elif ext == ".flac":
        content_type = "audio/flac"
    stream = open(temp_path, "rb")
    # Unlink immediately so temp streaming files do not accumulate on disk.
    try:
        os.unlink(temp_path)
    except OSError:
        pass
    return FileResponse(stream, content_type=content_type)


@login_required
@require_http_methods(["GET", "POST"])
def document_workspace(request: HttpRequest):
    services = _services(request)
    if request.method == "POST":
        action = request.POST.get("action", "upload")
        if action == "upload":
            files = request.FILES.getlist("document_files")
            if not files:
                messages.error(request, "Select at least one document.")
                return redirect("lectures:documents")
            lecture_id = _parse_int(request.POST.get("lecture_id", ""))
            try:
                ids = services.document_service.store_uploaded_files(
                    files, lecture_id=lecture_id
                )
                messages.success(request, f"Uploaded {len(ids)} document(s).")
                return redirect("lectures:documents")
            except Exception as exc:
                messages.error(request, f"Upload failed: {exc}")
        elif action == "correct_documents":
            lecture_id = _parse_int(request.POST.get("lecture_id", ""))
            if not lecture_id:
                messages.error(request, "Select a lecture first.")
            else:
                try:
                    count = services.document_service.correct_documents_for_lecture(
                        lecture_id
                    )
                    messages.success(request, f"Corrected {count} document(s).")
                    return redirect("lectures:documents")
                except Exception as exc:
                    messages.error(request, f"Correction failed: {exc}")
        elif action == "delete":
            doc_id = _parse_int(request.POST.get("doc_id", ""))
            if not doc_id:
                messages.error(request, "Select a document to delete.")
            else:
                try:
                    services.document_service.delete_document(doc_id)
                    messages.success(request, "Document deleted.")
                    return redirect("lectures:documents")
                except Exception as exc:
                    messages.error(request, f"Delete failed: {exc}")

    documents = services.repository.list_documents()
    selected_id = _parse_int(request.GET.get("doc_id", ""))
    preview_text = ""
    if selected_id:
        for doc in documents:
            if doc["id"] == selected_id:
                preview_text = doc.get("extracted_text", "")
                break

    return render(
        request,
        "lectures/documents.html",
        {
            "documents": documents,
            "courses": services.repository.list_courses(),
            "lectures": services.repository.list_lectures(),
            "selected_doc_id": selected_id,
            "preview_text": preview_text,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def course_detail(request: HttpRequest, course_id: int):
    services = _services(request)
    course = services.repository.get_course(course_id)
    if not course:
        raise Http404("Course not found")

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "rename_course":
            try:
                services.repository.rename_course(course_id, request.POST.get("title", ""))
                messages.success(request, "Course renamed.")
                return redirect("lectures:course_detail", course_id=course_id)
            except Exception as exc:
                messages.error(request, str(exc))
        elif action == "delete_course":
            try:
                services.repository.delete_course(course_id)
                messages.success(request, "Course deleted.")
                return redirect("lectures:dashboard")
            except Exception as exc:
                messages.error(request, str(exc))
        elif action == "create_lecture":
            try:
                services.repository.create_lecture(course_id, request.POST.get("title", ""))
                messages.success(request, "Lecture created.")
                return redirect("lectures:course_detail", course_id=course_id)
            except Exception as exc:
                messages.error(request, str(exc))
        elif action == "rename_lecture":
            lecture_id = _parse_int(request.POST.get("lecture_id", ""))
            if not lecture_id:
                messages.error(request, "Lecture not found.")
            else:
                try:
                    services.repository.rename_lecture(
                        lecture_id, request.POST.get("title", "")
                    )
                    messages.success(request, "Lecture renamed.")
                    return redirect("lectures:course_detail", course_id=course_id)
                except Exception as exc:
                    messages.error(request, str(exc))
        elif action == "delete_lecture":
            lecture_id = _parse_int(request.POST.get("lecture_id", ""))
            if not lecture_id:
                messages.error(request, "Lecture not found.")
            else:
                try:
                    services.repository.delete_lecture(lecture_id)
                    messages.success(request, "Lecture deleted.")
                    return redirect("lectures:course_detail", course_id=course_id)
                except Exception as exc:
                    messages.error(request, str(exc))

    lectures = services.repository.list_lectures(
        course_id=course_id, with_transcripts=True
    )
    return render(
        request,
        "lectures/course_detail.html",
        {"course": course, "lectures": lectures},
    )


@login_required
@require_http_methods(["GET", "POST"])
def notes_view(request: HttpRequest):
    services = _services(request)
    transcript_lectures = services.repository.list_lectures(with_transcripts=True)
    content = None
    selected_lecture_id = None
    selected_audio_id = None
    mode = NOTE_MODE_REFORMULATED

    if request.method == "POST":
        action = request.POST.get("action", "generate")
        selected_lecture_id = _parse_int(request.POST.get("lecture_id", ""))
        mode = request.POST.get("mode", NOTE_MODE_REFORMULATED)

        if not selected_lecture_id:
            messages.error(request, "Select a lecture with a transcript.")
        else:
            lecture = services.repository.get_lecture(selected_lecture_id)
            selected_audio_id = lecture.primary_audio_id if lecture else None
            if not selected_audio_id:
                messages.error(request, "Selected lecture has no transcript yet.")
            elif action == "load":
                latest = services.repository.get_latest_note(selected_audio_id, mode)
                content = latest.get("content") if latest else None
                if not content:
                    messages.info(request, "No saved notes for this lecture and mode.")
            else:
                try:
                    content = services.notes_service.generate_notes(selected_audio_id, mode)
                    messages.success(request, "Notes generated.")
                except Exception as exc:
                    messages.error(request, str(exc))
    elif transcript_lectures:
        selected_lecture_id = transcript_lectures[0]["id"]
        selected_audio_id = transcript_lectures[0]["primary_audio_id"]
        latest = (
            services.repository.get_latest_note(selected_audio_id)
            if selected_audio_id
            else None
        )
        if latest:
            content = latest.get("content")
            mode = latest.get("mode", NOTE_MODE_REFORMULATED)

    return render(
        request,
        "lectures/notes.html",
        {
            "lectures": transcript_lectures,
            "content": content,
            "selected_lecture_id": selected_lecture_id,
            "mode": mode,
            "modes": [
                (NOTE_MODE_EXACT, "Exact teacher wording"),
                (NOTE_MODE_REFORMULATED, "Reformulated version"),
            ],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def flashcards_view(request: HttpRequest):
    services = _services(request)
    transcript_lectures = services.repository.list_lectures(with_transcripts=True)
    cards: list[dict[str, str]] = []
    selected_lecture_id = None
    focus = ""
    count = 12

    if request.method == "POST":
        action = request.POST.get("action", "generate")
        selected_lecture_id = _parse_int(request.POST.get("lecture_id", ""))
        focus = request.POST.get("focus", "").strip()
        try:
            count = int(request.POST.get("count", 12))
        except (TypeError, ValueError):
            count = 12

        if not selected_lecture_id:
            messages.error(request, "Select a lecture with a transcript.")
        elif action == "load":
            cards = services.repository.list_flashcards(selected_lecture_id)
            if not cards:
                messages.info(request, "No flashcards saved for this lecture.")
        else:
            try:
                cards = services.flashcard_service.generate_flashcards(
                    lecture_id=selected_lecture_id,
                    count=count,
                    focus=focus or None,
                )
                messages.success(request, "Flashcards generated.")
            except Exception as exc:
                messages.error(request, str(exc))
    elif transcript_lectures:
        selected_lecture_id = transcript_lectures[0]["id"]
        cards = services.repository.list_flashcards(selected_lecture_id)

    return render(
        request,
        "lectures/flashcards.html",
        {
            "lectures": transcript_lectures,
            "selected_lecture_id": selected_lecture_id,
            "cards": cards,
            "focus": focus,
            "count": count,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def quiz_view(request: HttpRequest):
    services = _services(request)
    transcript_lectures = services.repository.list_lectures(with_transcripts=True)
    content = None
    quiz_items: list = []
    selected_lecture_id = None
    selected_audio_id = None
    num_questions = 10
    difficulty = "mixed"
    focus = ""

    if request.method == "POST":
        action = request.POST.get("action", "generate")
        selected_lecture_id = _parse_int(request.POST.get("lecture_id", ""))
        num_questions = int(request.POST.get("num_questions", 10))
        focus = request.POST.get("focus", "").strip()
        difficulty = request.POST.get("difficulty", "mixed").strip() or "mixed"

        if not selected_lecture_id:
            messages.error(request, "Select a lecture with a transcript.")
        else:
            lecture = services.repository.get_lecture(selected_lecture_id)
            selected_audio_id = lecture.primary_audio_id if lecture else None
            if not selected_audio_id:
                messages.error(request, "Selected lecture has no transcript yet.")
            elif action == "load":
                latest = services.repository.get_latest_quiz(audio_id=selected_audio_id)
                if latest:
                    content = latest.get("content")
                    quiz_items = parse_quiz_markdown(content or "")
                else:
                    messages.info(request, "No saved quiz for this lecture.")
            else:
                try:
                    content = services.quiz_service.generate_quiz(
                        audio_id=selected_audio_id,
                        num_questions=num_questions,
                        focus=focus or None,
                        difficulty=difficulty,
                    )
                    quiz_items = parse_quiz_markdown(content)
                    messages.success(request, "Quiz generated.")
                except Exception as exc:
                    messages.error(request, str(exc))
    elif transcript_lectures:
        selected_lecture_id = transcript_lectures[0]["id"]
        selected_audio_id = transcript_lectures[0]["primary_audio_id"]
        latest = (
            services.repository.get_latest_quiz(audio_id=selected_audio_id)
            if selected_audio_id
            else None
        )
        if latest:
            content = latest.get("content")
            quiz_items = parse_quiz_markdown(content or "")

    return render(
        request,
        "lectures/quiz.html",
        {
            "lectures": transcript_lectures,
            "content": content,
            "quiz_items": quiz_items,
            "selected_lecture_id": selected_lecture_id,
            "num_questions": num_questions,
            "difficulty": difficulty,
            "focus": focus,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def chat_view(request: HttpRequest):
    services = _services(request)
    lectures = services.repository.list_lectures()
    messages_list: list[dict[str, str]] = request.session.get("chat_messages", [])
    selected_lecture_id = _parse_int(
        request.POST.get("lecture_id", "")
        if request.method == "POST"
        else request.GET.get("lecture_id", "")
    )
    selected_audio_id = None
    if selected_lecture_id:
        lecture = services.repository.get_lecture(selected_lecture_id)
        selected_audio_id = lecture.primary_audio_id if lecture else None

    if request.method == "POST":
        action = request.POST.get("action", "send")
        if action == "clear":
            request.session["chat_messages"] = []
            request.session.modified = True
            return redirect("lectures:chat")

        question = request.POST.get("question", "").strip()
        if question:
            messages_list.append({"role": "user", "text": question})
            try:
                result = services.rag_service.answer_question(
                    question, audio_id=selected_audio_id
                )
                answer = str(result.get("answer", ""))
                sources = ", ".join(result.get("sources", []))
                if sources:
                    answer = f"{answer}\n\nSources: {sources}"
                messages_list.append({"role": "assistant", "text": answer})
            except Exception as exc:
                messages_list.append({"role": "assistant", "text": str(exc)})
            request.session["chat_messages"] = messages_list
            request.session.modified = True
        return redirect(
            f"{request.path}?lecture_id={selected_lecture_id}"
            if selected_lecture_id
            else request.path
        )

    return render(
        request,
        "lectures/chat.html",
        {
            "lectures": lectures,
            "chat_messages": messages_list,
            "selected_lecture_id": selected_lecture_id,
        },
    )


@login_required
def api_health(request: HttpRequest):
    health = ApiStatusService(GroqClient.from_settings()).check_health()
    return JsonResponse({"state": health.state, "message": health.message})


@login_required
@require_http_methods(["POST"])
def api_chat(request: HttpRequest):
    services = _services(request)
    message = request.POST.get("message", "").strip()
    if not message:
        return JsonResponse({"error": "Message required."}, status=400)
    lecture_id = _parse_int(request.POST.get("lecture_id", ""))
    audio_id = None
    if lecture_id:
        lecture = services.repository.get_lecture(lecture_id)
        audio_id = lecture.primary_audio_id if lecture else None
    try:
        result = services.rag_service.answer_question(message, audio_id=audio_id)
        answer = str(result.get("answer", "")).strip()
        sources = result.get("sources", [])
        return JsonResponse({"answer": answer, "sources": sources})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
