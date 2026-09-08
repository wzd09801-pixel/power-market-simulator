from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.app.core.config import Settings
from backend.app.storage import blob_store
from backend.app.storage.blob_store import BlobStoreError, MinioBlobStore


class ExistingBucketError(RuntimeError):
    code = "BucketAlreadyOwnedByYou"


class FakeMinioClient:
    def __init__(self, *, bucket_exists: bool, make_bucket_error: Exception | None = None) -> None:
        self._bucket_exists = bucket_exists
        self._make_bucket_error = make_bucket_error
        self.puts: list[tuple[str, str, bytes, str]] = []

    def bucket_exists(self, _bucket_name: str) -> bool:
        return self._bucket_exists

    def make_bucket(self, _bucket_name: str) -> None:
        if self._make_bucket_error is not None:
            raise self._make_bucket_error

    def put_object(
        self,
        bucket_name: str,
        object_key: str,
        body: Any,
        length: int,
        *,
        content_type: str,
    ) -> None:
        self.puts.append((bucket_name, object_key, cast(bytes, body.read(length)), content_type))


def _build_store(monkeypatch: pytest.MonkeyPatch, client: FakeMinioClient) -> MinioBlobStore:
    monkeypatch.setattr(
        blob_store,
        "import_module",
        lambda _name: SimpleNamespace(Minio=lambda *_args, **_kwargs: client),
    )
    return MinioBlobStore(Settings())


def test_minio_store_tolerates_concurrent_bucket_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeMinioClient(bucket_exists=False, make_bucket_error=ExistingBucketError())
    store = _build_store(monkeypatch, client)

    store.put(object_key="raw/example", content=b"payload", media_type="text/plain")

    assert client.puts == [("power-market-raw", "raw/example", b"payload", "text/plain")]


def test_minio_store_wraps_sdk_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeMinioClient(bucket_exists=False, make_bucket_error=RuntimeError("offline"))
    store = _build_store(monkeypatch, client)

    with pytest.raises(BlobStoreError, match="MinIO object write failed"):
        store.put(object_key="raw/example", content=b"payload", media_type="text/plain")
