"""Mock partner webhook server.

Simulates Slack incoming webhooks and PagerDuty Events API v2 with tunable
failure modes driven by environment variables. Used by docker-compose for
local partner-integration demos and by Phase 7 incident simulations.
"""

import hashlib
import hmac
import json
import logging
import os
import random
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mock-partner")

FAILURE_MODE = os.getenv("FAILURE_MODE", "none")  # none | 500 | timeout | slow
FAILURE_RATE = float(os.getenv("FAILURE_RATE", "0.0"))
HMAC_KEY = os.getenv("HMAC_SIGNING_KEY", "local-dev-only-not-a-real-secret")
VERIFY_SIGNATURE = os.getenv("VERIFY_SIGNATURE", "true").lower() == "true"

app = FastAPI(title="PGSCP mock partner", version="0.1.0")


def _verify(body: bytes, timestamp: str, signature: str) -> bool:
    mac = hmac.new(HMAC_KEY.encode(), msg=f"{timestamp}.".encode() + body, digestmod=hashlib.sha256)
    expected = f"v1={mac.hexdigest()}"
    return hmac.compare_digest(expected, signature)


def _maybe_fail():
    if FAILURE_MODE == "none":
        return
    if random.random() >= FAILURE_RATE:
        return
    if FAILURE_MODE == "500":
        raise HTTPException(status_code=500, detail="mock partner: simulated 500")
    if FAILURE_MODE == "timeout":
        time.sleep(30)  # caller will timeout long before this
    if FAILURE_MODE == "slow":
        time.sleep(3)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "failure_mode": FAILURE_MODE, "failure_rate": FAILURE_RATE}


async def _handle(request: Request, partner: str) -> JSONResponse:
    body = await request.body()
    timestamp = request.headers.get("x-pgscp-timestamp", "")
    signature = request.headers.get("x-pgscp-signature", "")
    idem = request.headers.get("x-pgscp-idempotency-key", "")

    if VERIFY_SIGNATURE:
        if not timestamp or not signature:
            raise HTTPException(status_code=401, detail="missing signature headers")
        if not _verify(body, timestamp, signature):
            raise HTTPException(status_code=401, detail="invalid signature")

    _maybe_fail()

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json") from None

    log.info(
        "delivery.received partner=%s idempotency_key=%s bytes=%d signature_ok=%s",
        partner,
        idem,
        len(body),
        VERIFY_SIGNATURE,
    )
    log.info("delivery.payload partner=%s body=%s", partner, json.dumps(parsed)[:500])
    return JSONResponse({"status": "ok", "partner": partner, "idempotency_key": idem})


@app.post("/slack/webhook")
async def slack_webhook(request: Request) -> JSONResponse:
    return await _handle(request, "slack")


@app.post("/pagerduty/v2/enqueue")
async def pagerduty_enqueue(request: Request) -> JSONResponse:
    return await _handle(request, "pagerduty")
