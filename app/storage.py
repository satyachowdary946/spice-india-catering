from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from urllib.parse import quote

import boto3
from botocore.config import Config


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    endpoint_url: str
    public_base_url: str


def r2_settings() -> R2Settings | None:
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.getenv("R2_BUCKET_NAME", "").strip()
    endpoint_url = os.getenv("R2_ENDPOINT_URL", "").strip()
    public_base_url = os.getenv("R2_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not (access_key_id and secret_access_key and bucket and (account_id or endpoint_url)):
        return None
    if not endpoint_url:
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    return R2Settings(
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket=bucket,
        endpoint_url=endpoint_url,
        public_base_url=public_base_url,
    )


def r2_configured() -> bool:
    return r2_settings() is not None


def _client(settings: R2Settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def put_bytes(key: str, data: bytes, content_type: str, cache_control: str = "public, max-age=31536000, immutable") -> str:
    settings = r2_settings()
    if not settings:
        raise RuntimeError("Cloudflare R2 is not configured.")
    _client(settings).put_object(
        Bucket=settings.bucket,
        Key=key,
        Body=data,
        ContentType=content_type or "application/octet-stream",
        CacheControl=cache_control,
    )
    return object_reference(key)


def get_bytes(key: str) -> tuple[bytes, str]:
    settings = r2_settings()
    if not settings:
        raise RuntimeError("Cloudflare R2 is not configured.")
    response = _client(settings).get_object(Bucket=settings.bucket, Key=key)
    data = response["Body"].read()
    content_type = response.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream"
    return data, content_type


def object_reference(key: str) -> str:
    settings = r2_settings()
    if settings and settings.public_base_url:
        return f"{settings.public_base_url}/{quote(key, safe='/')}"
    return f"r2://{key}"


def key_from_reference(reference: str) -> str | None:
    value = (reference or "").strip()
    if value.startswith("r2://"):
        return value[5:]
    settings = r2_settings()
    if settings and settings.public_base_url and value.startswith(settings.public_base_url + "/"):
        return value[len(settings.public_base_url) + 1 :]
    return None


def extension_for_content_type(content_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mapping.get((content_type or "").lower(), mimetypes.guess_extension(content_type or "") or ".bin")
