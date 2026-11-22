"""fastembed (ONNX) embedding service — same BGE model as M1, no PyTorch."""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Protocol, Sequence

from app.config import Settings, get_settings

log = logging.getLogger(__name__)
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    @property
    def model_name(self) -> str: ...
    @property
    def dimension(self) -> int: ...


class EmbeddingService:
    def __init__(self, model_name: str | None = None, *, settings: Settings | None = None, model: object | None = None) -> None:
        cfg = settings or get_settings()
        self._model_name = model_name or cfg.embedding_model_name
        self._batch_size = cfg.embedding_batch_size
        self._model = model
        self._dimension: int | None = None
        self._load_lock = threading.Lock()   # warm-up and the first question must not load the model twice

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_documents(["dimension probe"])[0])
        return self._dimension

    def _get_model(self):
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    from fastembed import TextEmbedding
                    log.info("Loading embedding model: %s", self._model_name)
                    self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._get_model().embed(list(texts), batch_size=self._batch_size)
        return [[float(x) for x in v] for v in vecs]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([f"{_BGE_QUERY_INSTRUCTION}{text.strip()}"])[0]


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
