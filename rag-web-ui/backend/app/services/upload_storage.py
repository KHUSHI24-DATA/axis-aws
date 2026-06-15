"""Local disk or S3-backed temporary upload storage."""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

S3_URI_PREFIX = "s3://"


def is_s3_uri(path: str) -> bool:
    return path.startswith(S3_URI_PREFIX)


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not is_s3_uri(uri):
        raise ValueError(f"Not an S3 URI: {uri}")
    without_scheme = uri[len(S3_URI_PREFIX) :]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def build_s3_uri(bucket: str, key: str) -> str:
    return f"{S3_URI_PREFIX}{bucket}/{key}"


class UploadStorage:
    def __init__(self) -> None:
        self._backend = (settings.UPLOAD_STORAGE or "local").strip().lower()
        self._bucket = settings.S3_UPLOAD_BUCKET
        self._region = settings.AWS_REGION or os.environ.get("AWS_REGION", "ap-south-1")
        self._s3_client = None

    @property
    def uses_s3(self) -> bool:
        return self._backend == "s3"

    def _get_s3_client(self):
        if self._s3_client is None:
            self._s3_client = boto3.client("s3", region_name=self._region)
        return self._s3_client

    def _local_root(self) -> Path:
        return Path(settings.LOCAL_UPLOAD_DIR)

    def temp_object_key(self, kb_id: int, file_name: str) -> str:
        return f"kb_{kb_id}/temp/{file_name}"

    def save_temp_bytes(self, kb_id: int, file_name: str, content: bytes) -> str:
        if self.uses_s3:
            if not self._bucket:
                raise ValueError("S3_UPLOAD_BUCKET is required when UPLOAD_STORAGE=s3")
            key = self.temp_object_key(kb_id, file_name)
            self._get_s3_client().put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
            )
            uri = build_s3_uri(self._bucket, key)
            logger.info("Stored upload at %s", uri)
            return uri

        temp_dir = self._local_root() / f"kb_{kb_id}" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_path = temp_dir / file_name
        local_path.write_bytes(content)
        return str(local_path)

    def read_bytes(self, storage_path: str) -> bytes:
        if is_s3_uri(storage_path):
            bucket, key = parse_s3_uri(storage_path)
            response = self._get_s3_client().get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        return Path(storage_path).read_bytes()

    def exists(self, storage_path: str) -> bool:
        if is_s3_uri(storage_path):
            bucket, key = parse_s3_uri(storage_path)
            try:
                self._get_s3_client().head_object(Bucket=bucket, Key=key)
                return True
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                    return False
                raise
        return os.path.exists(storage_path)

    def delete(self, storage_path: str) -> None:
        if not storage_path:
            return
        try:
            if is_s3_uri(storage_path):
                bucket, key = parse_s3_uri(storage_path)
                self._get_s3_client().delete_object(Bucket=bucket, Key=key)
                return
            if os.path.exists(storage_path):
                os.remove(storage_path)
        except OSError as exc:
            logger.warning("Failed to delete %s: %s", storage_path, exc)
        except ClientError as exc:
            logger.warning("Failed to delete S3 object %s: %s", storage_path, exc)

    def delete_kb_prefix(self, kb_id: int) -> None:
        if self.uses_s3:
            if not self._bucket:
                return
            prefix = f"kb_{kb_id}/"
            client = self._get_s3_client()
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                objects = page.get("Contents") or []
                if not objects:
                    continue
                client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                )
            return

        kb_upload_dir = self._local_root() / f"kb_{kb_id}"
        if not kb_upload_dir.exists():
            return
        for path in kb_upload_dir.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        for path in sorted(kb_upload_dir.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        kb_upload_dir.rmdir()

    @contextmanager
    def local_path_from_bytes(
        self, file_bytes: bytes, suffix: str = ".bin"
    ) -> Generator[str, None, None]:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_path = tmp.name
        try:
            tmp.write(file_bytes)
            tmp.close()
            yield tmp_path
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @contextmanager
    def local_path_for_reading(self, storage_path: str) -> Generator[str, None, None]:
        if not is_s3_uri(storage_path):
            yield storage_path
            return

        bucket, key = parse_s3_uri(storage_path)
        suffix = Path(key).suffix or ".bin"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_path = tmp.name
        tmp.close()
        try:
            self._get_s3_client().download_file(bucket, key, tmp_path)
            yield tmp_path
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


upload_storage = UploadStorage()
