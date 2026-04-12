# Architecture overview

## Purpose

PGSCP is a real-time event ingestion and alerting platform. It accepts events from partner systems, applies rule-based anomaly detection, persists alerts, and notifies an external partner API. It is deliberately shaped around a real operational pattern so that every architectural decision — networking, IAM, queueing, deployment safety, observability — can be defended in an interview.

## Component map

| Component | Purpose | AWS service |
|---|---|---|
| Edge | TLS termination, optional caching, origin protection | CloudFront → ALB |
| Ingestion API | Validate, persist raw payload, enqueue work | ECS Fargate (FastAPI) |
| Raw storage | Durable archive of inbound payloads | S3 (SSE-KMS) |
| Work queue | Async buffering, failure isolation | SQS (+ DLQ) |
| Worker | Rule engine, alert creation, partner delivery | ECS Fargate |
| Transactional store | Alerts, audit, delivery attempts | RDS PostgreSQL |
| Secrets | DB creds, partner API key, HMAC signing key | Secrets Manager |
| Observability | Logs, metrics, dashboards, alarms | CloudWatch (+ X-Ray via ADOT) |
| Audit | Control plane event log | CloudTrail |
| Registry | Container images | ECR |
| Private AWS access | Reduce NAT egress, harden network | VPC endpoints (S3, ECR, Secrets, Logs, SQS) |

## Traffic flow

1. Client sends HTTPS `POST /events` to CloudFront.
2. CloudFront forwards to ALB with a custom secret header; ALB listener rule rejects direct-to-origin requests missing that header.
3. ALB routes to API target group (ECS Fargate tasks in private app subnets). Target health is gated by `GET /health`.
4. API validates payload, generates `event_id`, writes raw JSON to S3 at `raw/device_id=.../dt=.../event_id.json`.
5. API sends an SQS message containing the S3 key, `event_id`, `device_id`, `timestamp`, `schema_version`, `idempotency_key`, and `traceparent`.
6. API returns `202 Accepted` with `event_id` and `trace_id`.
7. Worker long-polls SQS (`WaitTimeSeconds=20`), reads the raw payload from S3, runs the rule engine, and persists alerts + audit rows to RDS. Idempotency is enforced by a unique constraint on `idempotency_key`.
8. Worker calls the external partner API with HMAC-signed body, strict timeouts, exponential backoff + jitter, and a circuit breaker. Delivery attempts are recorded in `partner_delivery_attempts`.
9. Repeated failures exhaust `maxReceiveCount` and the message is moved to the DLQ for triage.
10. Logs and metrics are emitted to CloudWatch throughout; traces propagate via OTel `traceparent` in SQS message attributes.

## Network layout

- **1 VPC**, 2 Availability Zones
- **Public subnets**: ALB, NAT Gateway (1 in dev, 2 in prod)
- **Private app subnets**: ECS Fargate tasks (API, worker)
- **Private data subnets**: RDS Postgres
- **VPC endpoints** (interface + gateway): S3, ECR api, ECR dkr, Secrets Manager, CloudWatch Logs, SQS — reduces NAT egress and keeps AWS API traffic on the AWS backbone.

## Security boundaries

| Boundary | Enforcement |
|---|---|
| Public internet → ALB | HTTPS only, ACM cert, CloudFront custom header required |
| ALB → API tasks | Security group: ALB-SG → API-SG on container port only |
| API → RDS | SG-to-SG rule (API-SG → RDS-SG on 5432). RDS has no public access. |
| Worker → RDS | SG-to-SG rule (Worker-SG → RDS-SG on 5432) |
| Worker → Partner API | Outbound via NAT; HMAC signing; circuit breaker limits blast radius |
| ECS tasks → AWS APIs | Per-service IAM task roles, resource-scoped policies |
| CI/CD → AWS | GitHub OIDC only; no static keys in the repo or GitHub secrets |

## Failure isolation

- If the worker is degraded, the API continues to accept events (they accumulate in SQS until workers recover).
- If the partner API is down, the circuit breaker opens and deliveries are recorded as failed attempts; ingestion is unaffected.
- If the database is slow, worker processing slows but SQS absorbs the backpressure.
- If a deployment is unhealthy, ECS deployment circuit breaker auto-rolls-back to the previous task definition.

## Diagram

A rendered architecture diagram will be placed here once the system is deployed to dev. Until then, refer to the Mermaid source in [docs/blueprints/pgscp.md](../blueprints/pgscp.md).
