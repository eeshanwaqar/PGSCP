import hashlib
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from . import queue_sqs, storage_s3
from .observability import configure_logging, get_logger
from .schemas import IngestResponse, InferenceRecord
from .settings import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    get_logger(__name__).info("api.starting", settings=get_settings().model_dump())
    yield


app = FastAPI(title="PGSCP Ingestion API", version="0.1.0", lifespan=lifespan)
log = structlog.get_logger("pgscp.api")


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    trace_id = request.headers.get("traceparent", "").split("-")[1] if request.headers.get(
        "traceparent"
    ) else request_id.replace("-", "")[:32]

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, trace_id=trace_id)
    try:
        response: Response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()

    response.headers["x-request-id"] = request_id
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    # Shallow readiness — deeper checks (SQS reachability) can be added once we have
    # real infra. For local dev the happy path is sufficient.
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    # Stub: full Prometheus exposition will be wired in Phase 6 alongside CloudWatch EMF.
    return Response(content="# metrics placeholder\n", media_type="text/plain")


def _derive_idempotency_key(record: InferenceRecord, header_key: str | None) -> str:
    if header_key:
        return header_key
    basis = f"{record.request_id}|{record.model}|{record.timestamp.isoformat()}"
    return hashlib.sha256(basis.encode()).hexdigest()


@app.post("/events", response_model=IngestResponse, status_code=202)
async def ingest_event(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    raw = await request.body()
    settings = get_settings()
    if len(raw) > settings.max_payload_bytes:
        raise HTTPException(status_code=413, detail="payload too large")

    try:
        record = InferenceRecord.model_validate_json(raw)
    except Exception as exc:
        log.warning("ingest.validation_failed", error=str(exc))
        raise HTTPException(status_code=422, detail=f"invalid inference record: {exc}") from exc

    event_id = str(uuid.uuid4())
    idem = _derive_idempotency_key(record, idempotency_key)
    trace_id = structlog.contextvars.get_contextvars().get("trace_id", "")

    structlog.contextvars.bind_contextvars(
        event_id=event_id, model=record.model, idempotency_key=idem
    )

    s3_key = storage_s3.put_raw_event(record, event_id)
    log.info("ingest.s3_written", s3_key=s3_key)

    msg_id = queue_sqs.send_work_message(
        event_id=event_id,
        s3_key=s3_key,
        model=record.model,
        timestamp=record.timestamp.isoformat(),
        idempotency_key=idem,
        traceparent=request.headers.get("traceparent"),
    )
    log.info("ingest.enqueued", sqs_message_id=msg_id)

    return IngestResponse(event_id=event_id, trace_id=trace_id)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
    )
