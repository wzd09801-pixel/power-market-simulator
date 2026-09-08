from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Protocol, cast

import requests

from backend.app.core.config import get_settings


class EmbeddingClient(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def rerank(self, *, query: str, texts: list[str]) -> list[float]: ...


@dataclass(frozen=True)
class HashEmbeddingClient:
    model: str = "local-test-hash-v1"
    dimensions: int = 1024

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text, dimensions=self.dimensions) for text in texts]

    def rerank(self, *, query: str, texts: list[str]) -> list[float]:
        terms = {term for term in query.lower().split() if term}
        return [
            float(len(terms & set(text.lower().split()))) / max(len(terms), 1) for text in texts
        ]


class LocalEmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        reranker_model: str,
        timeout_seconds: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.reranker_model = reranker_model
        self.timeout_seconds = timeout_seconds

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = requests.post(
            f"{self.base_url}/embed",
            json={"model": self.model, "texts": texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return cast(list[list[float]], payload["embeddings"])

    def rerank(self, *, query: str, texts: list[str]) -> list[float]:
        response = requests.post(
            f"{self.base_url}/rerank",
            json={"model": self.reranker_model, "query": query, "texts": texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return cast(list[float], payload["scores"])


def get_embedding_client() -> EmbeddingClient:
    settings = get_settings()
    return LocalEmbeddingClient(
        base_url=settings.embedding_service_url,
        model=settings.embedding_model,
        reranker_model=settings.reranker_model,
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _hash_vector(text: str, *, dimensions: int) -> list[float]:
    digest = sha256(text.encode("utf-8")).digest()
    return [float(digest[index % len(digest)] - 127) / 127 for index in range(dimensions)]
