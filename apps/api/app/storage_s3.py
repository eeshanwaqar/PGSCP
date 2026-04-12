import json
from datetime import datetime, timezone

import boto3
from botocore.config import Config

from .schemas import InferenceRecord
from .settings import get_settings


def _client():
    settings = get_settings()
    kwargs = {
        "region_name": settings.aws_region,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client("s3", **kwargs)


def raw_key(record: InferenceRecord, event_id: str) -> str:
    dt = record.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
    # Slashes in the model name would corrupt the key structure
    safe_model = record.model.replace("/", "_")
    return f"raw/model={safe_model}/dt={dt}/{event_id}.json"


def put_raw_event(record: InferenceRecord, event_id: str) -> str:
    settings = get_settings()
    key = raw_key(record, event_id)
    body = record.model_dump_json().encode("utf-8")

    extra = {"ContentType": "application/json"}
    if settings.s3_kms_key_id:
        extra["ServerSideEncryption"] = "aws:kms"
        extra["SSEKMSKeyId"] = settings.s3_kms_key_id

    _client().put_object(
        Bucket=settings.s3_raw_bucket,
        Key=key,
        Body=body,
        **extra,
    )
    return key


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
