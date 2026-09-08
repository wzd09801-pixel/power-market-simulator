from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="Local BGE Embedding Service", version="0.1.0")
DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
DEFAULT_RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")


class EmbedRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = DEFAULT_MODEL
    texts: list[str] = Field(min_length=1, max_length=128)


class EmbedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    embeddings: list[list[float]]


class RerankRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = DEFAULT_RERANKER_MODEL
    query: str = Field(min_length=1, max_length=4000)
    texts: list[str] = Field(min_length=1, max_length=128)


class RerankResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    scores: list[float]


@lru_cache(maxsize=2)
def _load_model(model: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model, trust_remote_code=False)


@lru_cache(maxsize=2)
def _load_reranker(model: str) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model, trust_remote_code=False)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "default_model": DEFAULT_MODEL}


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    model = _load_model(request.model)
    embeddings = model.encode(request.texts, normalize_embeddings=True)
    return EmbedResponse(model=request.model, embeddings=embeddings.tolist())


@app.post("/rerank", response_model=RerankResponse)
def rerank(request: RerankRequest) -> RerankResponse:
    model = _load_reranker(request.model)
    scores = model.predict([(request.query, text) for text in request.texts])
    return RerankResponse(model=request.model, scores=scores.tolist())
