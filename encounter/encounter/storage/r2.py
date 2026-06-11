"""Cloudflare R2 storage backend (S3-compatible, via boto3).

boto3 is an optional dependency; it is imported lazily so the default local
setup needs nothing extra.
"""

from __future__ import annotations

from ..config import get_settings
from .base import ObjectStorage


class R2Storage(ObjectStorage):
    def __init__(self) -> None:
        import boto3  # type: ignore

        settings = get_settings()
        if not settings.r2_endpoint_url:
            raise RuntimeError("ENCOUNTER_R2_ENDPOINT_URL is required for R2 storage")
        self.bucket = settings.r2_bucket
        self.public_base = settings.storage_public_base_url.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )

    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        self._client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )
        return self.url_for(key)

    def get(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def url_for(self, key: str) -> str:
        return f"{self.public_base}/{key.lstrip('/')}"

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError  # type: ignore

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
