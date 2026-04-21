"""CloudWatch Logs Insights tool.

In local mode there is no CloudWatch — this tool returns a stub `[]` result with
a `source: "local-stub"` marker so the graph can proceed. In AWS dev/prod, the
same function hits real Logs Insights.
"""

import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from ..observability import get_logger
from ..settings import get_settings

log = get_logger(__name__)


def _client():
    s = get_settings()
    if s.env == "local" or s.aws_endpoint_url:
        return None  # LocalStack doesn't support CloudWatch Logs Insights reliably
    return boto3.client("logs", region_name=s.aws_region)


def query_logs(
    *,
    trace_id: str | None,
    log_group: str,
    window_minutes: int = 15,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Run a Logs Insights query filtered by trace_id; return up to `limit` rows.

    Returns an empty list (with a log line) when running locally or when Logs
    Insights is unavailable — never raises, so the graph can degrade gracefully.
    """
    client = _client()
    if client is None:
        log.info("tool.cloudwatch.local_stub", log_group=log_group)
        return []
    if not trace_id:
        return []

    now = int(time.time())
    start = now - window_minutes * 60
    query_string = (
        f"fields @timestamp, @message | filter trace_id = '{trace_id}' "
        f"| sort @timestamp asc | limit {limit}"
    )
    try:
        start_resp = client.start_query(
            logGroupName=log_group,
            startTime=start,
            endTime=now,
            queryString=query_string,
        )
        query_id = start_resp["queryId"]
    except ClientError as exc:
        log.warning("tool.cloudwatch.start_failed", error=str(exc))
        return []

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        result = client.get_query_results(queryId=query_id)
        status = result.get("status", "")
        if status in {"Complete", "Failed", "Cancelled"}:
            if status != "Complete":
                log.warning("tool.cloudwatch.query_status", status=status)
                return []
            return [
                {col["field"]: col["value"] for col in row if col["field"] != "@ptr"}
                for row in result.get("results", [])
            ]
        time.sleep(0.5)

    log.warning("tool.cloudwatch.query_timeout")
    return []
