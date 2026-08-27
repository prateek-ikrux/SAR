from __future__ import annotations

import logging
from datetime import timedelta
from functools import lru_cache

from minio import Minio
from minio.error import S3Error
from starlette.concurrency import run_in_threadpool

from app.config import settings

log = logging.getLogger(__name__)


class StorageError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@lru_cache
def _client() -> Minio:
    if not settings.minio_configured:
        raise StorageError("Object storage is not configured on this server.", status_code=503)
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def object_key(file_name: str) -> str:
    prefix = settings.minio_prefix.strip("/")
    return f"{prefix}/{file_name}" if prefix else file_name


def _presign(key: str) -> str:
    client = _client()
    # stat_object first so a missing file is a clean 404 rather than a signed
    # URL that 404s in the browser after the user clicks it.
    client.stat_object(settings.minio_bucket, key)
    return client.presigned_get_object(
        settings.minio_bucket, key, expires=timedelta(seconds=settings.minio_presign_expiry_seconds)
    )


async def presigned_resume_url(file_name: str) -> str:
    key = object_key(file_name)
    try:
        return await run_in_threadpool(_presign, key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
            raise StorageError(f"Resume '{file_name}' was not found in object storage.", 404) from exc
        log.exception("object storage error", extra={"key": key, "code": exc.code})
        raise StorageError("Could not retrieve the resume from object storage.") from exc
    except StorageError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface as a clean API error
        log.exception("object storage failure", extra={"key": key})
        raise StorageError("Could not retrieve the resume from object storage.") from exc


async def healthy() -> bool:
    if not settings.minio_configured:
        return False
    try:
        return await run_in_threadpool(_client().bucket_exists, settings.minio_bucket)
    except Exception:  # noqa: BLE001
        return False
