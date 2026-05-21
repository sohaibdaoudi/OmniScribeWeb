from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings

from core.config import load_settings
from core.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStoreService:
    """ChromaDB HTTP client (Docker) — collection semantics match desktop MVP."""

    def __init__(self) -> None:
        settings = load_settings()
        self._collection_name = settings.chroma_collection
        self.client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=Settings(anonymized_telemetry=False),
        )
        self.embedding_service = EmbeddingService()
        self.collection = self._open_collection()

    def _open_collection(self):
        """Open existing collection or create it once (Chroma 1.x safe)."""
        name = self._collection_name

        try:
            return self.client.get_collection(name=name)
        except Exception:
            pass

        try:
            return self.client.get_or_create_collection(name=name)
        except Exception as exc:
            message = str(exc).lower()
            if "already exists" in message:
                return self.client.get_collection(name=name)
            raise

    def _generate_chunk_id(self, source_label: str, chunk_index: int) -> str:
        return f"{source_label}::{chunk_index}"

    def add_chunks(self, chunks: list[tuple[str, str, str]]) -> None:
        if not chunks:
            return

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for i, (text, source_label, kind) in enumerate(chunks):
            chunk_id = self._generate_chunk_id(source_label, i)
            ids.append(chunk_id)
            texts.append(text)
            metadatas.append({"source_label": source_label, "kind": kind})

        embeddings = self.embedding_service.embed_documents(texts)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def delete_by_source(self, source_label: str) -> None:
        if not source_label:
            return
        try:
            self.collection.delete(where={"source_label": source_label})
            return
        except Exception as exc:
            logger.warning("Vector delete by source failed for %s: %s", source_label, exc)

        try:
            batch = self.collection.get(where={"source_label": source_label})
            ids = batch.get("ids") or []
            if ids:
                self.collection.delete(ids=ids)
        except Exception as exc:
            logger.warning("Vector delete fallback failed for %s: %s", source_label, exc)
            raise

    def similarity_search(
        self, query: str, top_k: int = 6
    ) -> list[tuple[str, dict[str, Any]]]:
        query_embedding = self.embedding_service.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        return [(doc, meta) for doc, meta in zip(documents, metadatas)]

    def clear_collection(self) -> None:
        """Empty the index for rebuild — delete records in-place when possible."""
        name = self._collection_name
        try:
            batch = self.collection.get()
            existing_ids = batch.get("ids") or []
            if existing_ids:
                self.collection.delete(ids=existing_ids)
                return
        except Exception as exc:
            logger.warning("In-place Chroma clear failed, recreating collection: %s", exc)

        try:
            self.client.delete_collection(name)
        except Exception:
            pass

        self.collection = self._open_collection()
