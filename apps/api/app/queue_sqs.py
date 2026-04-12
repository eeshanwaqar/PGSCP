import json

import boto3
from botocore.config import Config

from .settings import get_settings


def _client():
    settings = get_settings()
    kwargs = {
        "region_name": settings.aws_region,
        "config": Config(retries={"max_attempts": 3, "mode": "standard"}),
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client("sqs", **kwargs)


def send_work_message(
    *,
    event_id: str,
    s3_key: str,
    model: str,
    timestamp: str,
    idempotency_key: str,
    traceparent: str | None,
) -> str:
    """Enqueue a pointer to the raw event in S3. Returns the SQS message id."""
    settings = get_settings()

    body = json.dumps(
        {
            "event_id": event_id,
            "s3_bucket": settings.s3_raw_bucket,
            "s3_key": s3_key,
            "model": model,
            "timestamp": timestamp,
            "schema_version": "v1",
            "idempotency_key": idempotency_key,
        },
        separators=(",", ":"),
    )

    attrs: dict[str, dict] = {}
    if traceparent:
        attrs["traceparent"] = {"DataType": "String", "StringValue": traceparent}

    resp = _client().send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=body,
        MessageAttributes=attrs,
    )
    return resp["MessageId"]
