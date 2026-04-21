"""S3 tool — fetch the raw inference record archived by the API."""

import json
from typing import Any

import boto3
from botocore.config import Config

from ..settings import get_settings


def _client():
    s = get_settings()
    kwargs: dict[str, Any] = {
        "region_name": s.aws_region,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if s.aws_endpoint_url:
        kwargs["endpoint_url"] = s.aws_endpoint_url
    return boto3.client("s3", **kwargs)


def fetch_inference_record(bucket: str, key: str) -> dict[str, Any]:
    """Return the parsed JSON record at `s3://bucket/key`.

    The worker stores raw inference records under `raw/model=.../dt=.../event_id.json`.
    Keys and completions can be long — we truncate prompt/completion strings to
    2KB each before returning so they fit into LLM context windows cleanly.
    """
    resp = _client().get_object(Bucket=bucket, Key=key)
    raw = json.loads(resp["Body"].read())
    for field in ("prompt", "completion"):
        value = raw.get(field)
        if isinstance(value, str) and len(value) > 2048:
            raw[field] = value[:2048] + f"... [truncated {len(value) - 2048} chars]"
    return raw
