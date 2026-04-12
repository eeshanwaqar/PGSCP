from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import InferenceRecordRow


def try_claim_idempotency(
    session: Session,
    *,
    event_id: str,
    idempotency_key: str,
    model: str,
    provider: str,
    event_timestamp,
    latency_ms: int,
    cost_usd: float,
    prompt_tokens: int,
    completion_tokens: int,
    predicted_label: str | None,
    expected_label: str | None,
    s3_bucket: str,
    s3_key: str,
) -> bool:
    """Attempt to insert an inference-record row. Returns True on first write,
    False if a row with the same idempotency_key already exists.

    Relies on the unique constraint on `idempotency_key` to catch duplicates
    atomically — first writer wins, duplicates are cheap no-ops.
    """
    row = InferenceRecordRow(
        event_id=event_id,
        idempotency_key=idempotency_key,
        model=model,
        provider=provider,
        event_timestamp=event_timestamp,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        predicted_label=predicted_label,
        expected_label=expected_label,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return False
    return True
