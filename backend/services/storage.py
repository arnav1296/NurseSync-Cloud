"""Amazon S3: patient attachments and shift reports.

The browser uploads files straight to S3 with a short-lived presigned URL, so file
bytes never pass through the API server. Downloads use presigned GET URLs too; the
bucket itself is private.
"""

import asyncio
import json
import uuid
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from config import AWS_REGION, S3_BUCKET

UPLOAD_URL_SECONDS = 300
DOWNLOAD_URL_SECONDS = 900
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


class StorageUnavailable(Exception):
    """No bucket configured."""


@lru_cache(maxsize=1)
def _client():
    # regional endpoint + SigV4 so presigned URLs work right after bucket creation
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        endpoint_url=f"https://s3.{AWS_REGION}.amazonaws.com",
        config=Config(signature_version="s3v4"),
    )


def _require_bucket() -> str:
    if not S3_BUCKET:
        raise StorageUnavailable()
    return S3_BUCKET


def new_attachment_key(patient_id: str, file_name: str) -> str:
    safe = "".join(c for c in file_name if c.isalnum() or c in "._-")[-80:] or "file"
    return f"attachments/{patient_id}/{uuid.uuid4().hex}-{safe}"


def upload_url(key: str, content_type: str) -> str:
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": _require_bucket(), "Key": key, "ContentType": content_type},
        ExpiresIn=UPLOAD_URL_SECONDS,
    )


def download_url(key: str) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _require_bucket(), "Key": key},
        ExpiresIn=DOWNLOAD_URL_SECONDS,
    )


async def object_exists(key: str) -> bool:
    def _head() -> bool:
        try:
            _client().head_object(Bucket=_require_bucket(), Key=key)
            return True
        except ClientError:
            return False

    return await asyncio.to_thread(_head)


async def put_json(key: str, payload: dict) -> None:
    def _put() -> None:
        _client().put_object(
            Bucket=_require_bucket(),
            Key=key,
            Body=json.dumps(payload, indent=2, default=str).encode(),
            ContentType="application/json",
        )

    await asyncio.to_thread(_put)
