# OmniScribe Web MVP

Django fullstack migration of the OmniScribe desktop MVP. Business logic (transcription, OCR, RAG, notes, quiz) is ported from `OmniScribeDesktop/` with the same pipelines and environment variable names.

## Stack

| Layer | Technology |
|-------|------------|
| Web | Django 5 (MVT, server-rendered templates) |
| DB | PostgreSQL 16 |
| Files | MinIO |
| Vectors | ChromaDB (Docker, HTTP) |
| AI | Groq (Whisper + chat) |
| Embeddings / OCR | sentence-transformers + EasyOCR on **CPU only** |

## CPU-only runtime

This project is configured for **CPU-only** execution:

- PyTorch is installed from the official **CPU wheel index** (no CUDA builds).
- `CUDA_VISIBLE_DEVICES` is cleared in settings, Docker, and entrypoint.
- Embeddings use `device: "cpu"` (same as desktop).
- EasyOCR runs with `gpu=False`.

Do not install GPU/CUDA variants of PyTorch or enable GPU flags.

## Quick start (Docker)

```bash
cp .env.example .env
# Set GROQ_API_KEY in .env

docker compose up --build
```

Open http://localhost:8000 — register, then upload audio/documents.

Services:

- Web: http://localhost:8000
- MinIO console: http://localhost:9001
- ChromaDB: http://localhost:8001

## Local development (uv)

```bash
cp .env.example .env
# Start infrastructure only:
docker compose up db chroma minio minio-init -d

uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

## Project layout

```
config/           Django project settings & URLs
core/             Shared services (ported from desktop)
  services/       Groq, RAG, transcription, documents, notes, quiz
  storage.py      MinIO client
  repository.py   ORM layer matching desktop Database API
lectures/         Models & views for audio, documents, notes, quiz, chat
accounts/         Registration & login
OmniScribeDesktop/  Reference desktop MVP (source of truth for logic)
```

## Environment compatibility

These variables work the same as the desktop app:

- `GROQ_API_KEY`, `GROQ_WHISPER_MODEL`, `GROQ_CHAT_MODEL`
- `OMNISCRIBE_*` path prefixes (web uses MinIO; temp dir for processing)

Web-specific: `POSTGRES_*`, `MINIO_*`, `CHROMA_*`, `DJANGO_*`.
