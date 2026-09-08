from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from io import BytesIO
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from backend.app.core.config import Settings


class BlobStoreError(RuntimeError):
    pass


class BlobStore(Protocol):
    bucket_name: str

    def put(self, *, object_key: str, content: bytes, media_type: str) -> None: ...

    def get(self, *, object_key: str) -> bytes: ...


@dataclass
class MemoryBlobStore:
    bucket_name: str = "test-raw"

    def __post_init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, *, object_key: str, content: bytes, media_type: str) -> None:
        del media_type
        self._objects.setdefault(object_key, content)

    def get(self, *, object_key: str) -> bytes:
        return self._objects[object_key]


class MinioBlobStore:
    def __init__(self, settings: Settings) -> None:
        parsed = urlparse(settings.minio_endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("MINIO_ENDPOINT must be an HTTP or HTTPS URL.")
        module = import_module("minio")
        client_class = cast(Any, module.Minio)
        endpoint = parsed.netloc
        self._client = client_class(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=parsed.scheme == "https",
        )
        self.bucket_name = settings.minio_bucket

    def put(self, *, object_key: str, content: bytes, media_type: str) -> None:
        try:
            if not self._client.bucket_exists(self.bucket_name):
                try:
                    self._client.make_bucket(self.bucket_name)
                except Exception as exc:
                    if not _is_existing_bucket_error(exc):
                        raise
            self._client.put_object(
                self.bucket_name,
                object_key,
                BytesIO(content),
                len(content),
                content_type=media_type,
            )
        except Exception as exc:
            raise BlobStoreError(f"MinIO object write failed: {type(exc).__name__}.") from exc

    def get(self, *, object_key: str) -> bytes:
        try:
            response = self._client.get_object(self.bucket_name, object_key)
            try:
                return cast(bytes, response.read())
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            raise BlobStoreError(f"MinIO object read failed: {type(exc).__name__}.") from exc


def _is_existing_bucket_error(exc: Exception) -> bool:
    return getattr(exc, "code", None) in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}
