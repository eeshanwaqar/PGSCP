"""ECS tool — recent deployments for a service.

In local mode returns a scripted recent-deploy list so the graph has realistic
input. In AWS mode hits `ecs:DescribeServices` / `DescribeTaskDefinition` for the
real cluster+service.
"""

from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from ..observability import get_logger
from ..settings import get_settings

log = get_logger(__name__)

_LOCAL_STUB = [
    {
        "service": "api",
        "deployed_at": "2026-04-14T08:12:00Z",
        "image_sha": "sha256:local-stub-api-deadbeef",
        "status": "PRIMARY",
        "desired_count": 2,
        "running_count": 2,
    },
    {
        "service": "worker",
        "deployed_at": "2026-04-13T21:03:00Z",
        "image_sha": "sha256:local-stub-worker-cafebabe",
        "status": "PRIMARY",
        "desired_count": 2,
        "running_count": 2,
    },
]


def recent_deployments(*, service: str, hours: int = 24) -> list[dict[str, Any]]:
    s = get_settings()
    if s.env == "local" or s.aws_endpoint_url:
        log.info("tool.ecs.local_stub", service=service)
        return [d for d in _LOCAL_STUB if service in {"any", d["service"]}]

    client = boto3.client("ecs", region_name=s.aws_region)
    try:
        resp = client.describe_services(cluster=s.ecs_cluster, services=[service])
    except ClientError as exc:
        log.warning("tool.ecs.describe_failed", error=str(exc))
        return []

    deployments: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for svc in resp.get("services", []):
        for d in svc.get("deployments", []):
            deployed_at = d.get("createdAt") or now
            age_hours = (now - deployed_at).total_seconds() / 3600.0
            if age_hours > hours:
                continue
            deployments.append(
                {
                    "service": svc["serviceName"],
                    "deployed_at": deployed_at.isoformat(),
                    "task_definition": d.get("taskDefinition", ""),
                    "status": d.get("status", ""),
                    "desired_count": d.get("desiredCount", 0),
                    "running_count": d.get("runningCount", 0),
                    "rollout_state": d.get("rolloutState", ""),
                }
            )
    return deployments
