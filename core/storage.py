"""MinIO object storage (replaces desktop local filesystem storage)."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import BinaryIO

from django.conf import settings
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class ObjectStorage:
    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_file(
        self, *, prefix: str, source_path: Path, content_type: str | None = None
    ) -> str:
        extension = source_path.suffix or ""
        object_name = f"{prefix}/{uuid.uuid4().hex}{extension.lower()}"
        self.client.fput_object(
            self.bucket,
            object_name,
            str(source_path),
            content_type=content_type or "application/octet-stream",
        )
        return object_name

    def upload_stream(
        self,
        *,
        prefix: str,
        stream: BinaryIO,
        extension: str,
        length: int,
        content_type: str | None = None,
    ) -> str:
        object_name = f"{prefix}/{uuid.uuid4().hex}{extension.lower()}"
        self.client.put_object(
            self.bucket,
            object_name,
            stream,
            length,
            content_type=content_type or "application/octet-stream",
        )
        return object_name

    def download_to_path(self, object_name: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.fget_object(self.bucket, object_name, str(destination))
        return destination

    def get_local_copy(self, object_name: str, suffix: str = "") -> Path:
        """Download object to temp dir for processing pipelines."""
        temp_dir = settings.OMNISCRIBE_TEMP_DIR
        temp_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(object_name).suffix or suffix
        local_path = temp_dir / f"{uuid.uuid4().hex}{ext}"
        return self.download_to_path(object_name, local_path)

    def delete_object(self, object_name: str) -> None:
        if not object_name:
            return
        try:
            self.client.remove_object(self.bucket, object_name)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                logger.info("Object already removed: %s", object_name)
                return
            logger.warning("Failed to delete object %s: %s", object_name, exc)
            raise
        except Exception as exc:
            logger.warning("Failed to delete object %s: %s", object_name, exc)
            raise


_storage: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        _storage = ObjectStorage()
    return _storage
