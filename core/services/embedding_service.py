from __future__ import annotations

import os

from langchain_community.embeddings import HuggingFaceEmbeddings

# CPU-only before any torch import side effects
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


class EmbeddingService:
    """Singleton sentence-transformer embeddings on CPU (desktop parity)."""

    _instance = None

    def __new__(cls, model_name: str = "all-MiniLM-L6-v2") -> EmbeddingService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize(model_name)
        return cls._instance

    def _initialize(self, model_name: str) -> None:
        self.model_name = model_name
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    def embed_query(self, text: str) -> list[float]:
        return self.embeddings.embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(texts)
