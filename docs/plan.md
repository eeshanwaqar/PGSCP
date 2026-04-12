# PGSCP — Production-Grade Secure Cloud Platform

## Context

Portfolio project to prove Cloud Engineer ownership end-to-end: AWS infra via Terraform, secure CI/CD, IAM least-privilege, observability, reliability, incident response. Two blueprints reviewed (Cloud Engineer Project Blueprint + PGSCP). PGSCP is the authoritative design; this plan synthesizes both into an executable build order.

**System shape:** `POST /events` → FastAPI (ECS Fargate) → S3 (raw payload) + SQS → Worker (ECS Fargate) → rules → RDS Postgres + outbound partner API (with retries / idempotency / circuit breaker), DLQ for poison messages, CloudWatch + CloudTrail for ops/audit.

**User decisions locked in:**
- Deploy target: **real AWS, dev environment** (tear down between sessions to control cost)
- Environments: **dev + prod** (prod gated by manual approval; may stay `terraform plan`-only until late)
- Stretch items in scope: **VPC endpoints**, **OpenTelemetry → X-Ray via ADOT**, **CloudFront in front of ALB**
- Build order: **app-first** (local docker-compose working before any Terraform apply)

---

## Target architecture (confirmed)

```
Client → CloudFront → ALB (public subnet, HTTPS via ACM)
                         ↓
             ECS Fargate: API (private app subnet)
                 ├→ S3 (raw events, SSE-KMS)
                 └→ SQS main queue ──→ ECS Fargate: Worker (private app subnet)
                          ↓ redrive                    ├→ RDS Postgres (private data subnet, Multi-AZ off in dev)
                         DLQ                           ├→ Partner API (outbound via NAT)
                                                       └→ CloudWatch logs/metrics
VPC endpoints: S3 (gateway), ECR, Secrets Manager, CloudWatch Logs, SQS (interface)
CloudTrail → S3 logs bucket
Secrets Manager: db creds, partner API key, HMAC signing secret
```

2 AZs, 1 NAT in dev (cost), 2 NAT in prod (HA).

---

## Repository layout

```
pgscp/
  apps/
    api/          FastAPI service (Dockerfile, pyproject.toml, tests/)
    worker/       SQS consumer (Dockerfile, pyproject.toml, tests/)
  infra/
    bootstrap/    One-time: tfstate S3 bucket + KMS key + GitHub OIDC role
    envs/
      dev/
      prod/
    modules/
      network/ iam/ ecr/ alb/ ecs_service/ sqs/ rds/ s3/ secrets/
      cloudwatch/ cloudtrail/ vpc_endpoints/ cloudfront/
  .github/workflows/   ci.yml, terraform-plan.yml, deploy-dev.yml, deploy-prod.yml
  local/               docker-compose.yml (api + worker + localstack + postgres + mock partner)
  docs/
    architecture/overview.md
    decisions/         ADRs: ECS-vs-EKS, SQS-vs-Kafka, RDS-vs-Dynamo, Secrets-Mgr-vs-SSM
    runbooks/          deploy, rollback, partner-outage, queue-backlog, db-issue
    postmortems/       template.md + one real simulated incident
  README.md SECURITY.md
```

---

## Implementation phases

### Phase 0 — Repo foundation (½ day)
- `git init`, create tree above, `.gitignore`, `.editorconfig`, `pre-commit` (ruff, terraform fmt, tflint, gitleaks).
- README stub with architecture diagram placeholder.
- ADR template + write ADR-001 (ECS vs EKS), ADR-002 (SQS vs Kafka).

### Phase 1 — App services, local-first (Week A)
**API (`apps/api`)** — FastAPI
- Endpoints: `POST /events`, `GET /alerts`, `GET /health` (liveness), `GET /ready` (dependency check), `GET /metrics` (Prometheus or EMF).
- `schemas.py`: Pydantic event/alert models with `schema_version`.
- `storage_s3.py`: boto3 write raw payload, partition key `raw/device_id=.../dt=.../event_id.json`.
- `queue_sqs.py`: send message with `event_id`, S3 key, `idempotency_key`, `traceparent`.
- `settings.py`: pydantic-settings, env-driven, never read secrets from disk.
- `observability.py`: structlog JSON logger with correlation IDs; OTel FastAPI auto-instrumentation.
- Returns `202 Accepted` with `event_id` + `trace_id`.

**Worker (`apps/worker`)**
- Long-poll loop (`WaitTimeSeconds=20`), visibility timeout > max processing time.
- `processor.py`: rule engine — hard threshold, rate-of-change, stuck sensor, missing heartbeat.
- `dedupe.py`: Postgres unique constraint on `idempotency_key` (handles SQS at-least-once).
- `partner_client.py`: httpx with connect=1s/total=5s, exponential backoff + jitter, circuit breaker (`pybreaker`), HMAC signing over body+timestamp, `partner_request_id` idempotency header.
- DB tables: `events_audit`, `alerts`, `alert_events` (immutable transitions), `partner_delivery_attempts`.
- Alembic migrations.

**Local (`local/docker-compose.yml`)**
- Services: `api`, `worker`, `localstack` (SQS+S3+Secrets), `postgres`, `mock-partner` (tiny FastAPI that can return 200/500/timeout via env flag).
- Exit criteria: `docker compose up` → curl `/events` → worker processes → alert row appears in Postgres → mock partner receives signed request.

**Tests**: unit tests for rule engine + dedupe + partner client retries. Integration test using LocalStack SQS.

### Phase 2 — Terraform bootstrap + network + shared (Week C start)
- `infra/bootstrap/`: S3 tfstate bucket (versioning, SSE-KMS, public access block), KMS key, IAM OIDC provider for GitHub, `pgscp-github-oidc` role scoped to repo/branch.
- `modules/network/`: VPC, 2 AZs, public + private-app + private-data subnets, IGW, 1 NAT (dev) / 2 NAT (prod), route tables, security groups (alb-sg, api-sg, worker-sg, rds-sg with SG-to-SG rules only).
- `modules/vpc_endpoints/`: S3 gateway + interface endpoints for ECR api/dkr, Secrets Manager, CloudWatch Logs, SQS.
- `modules/s3/`: `pgscp-raw-events-<env>`, `pgscp-logs-<env>`; SSE-KMS, versioning, lifecycle to Glacier after 30d on raw bucket, block-public-access.
- `modules/iam/`: ECS task execution role (pull ECR, write logs), API task role (s3:PutObject scoped to raw prefix, sqs:SendMessage scoped to queue ARN, secretsmanager:GetSecretValue scoped to `pgscp/*`), worker task role (sqs consume, s3 get, secrets get, rds connect via secret).

### Phase 3 — Data + secrets + queue (Week C end)
- `modules/secrets/`: Secrets Manager entries for db creds (with rotation Lambda stub), partner API key, HMAC signing secret.
- `modules/rds/`: Postgres 16, encrypted (KMS), not publicly accessible, private data subnet group, SG allows only from worker-sg and api-sg, Multi-AZ=false in dev / true in prod, 7-day backups.
- `modules/sqs/`: main queue + DLQ with `maxReceiveCount=5`, KMS encryption, long-polling defaults.

### Phase 4 — Compute + traffic (Week D)
- `modules/ecr/`: two repos (`api`, `worker`), immutable tags, scan-on-push.
- `modules/alb/`: ALB in public subnets, HTTPS listener with ACM cert, target group for API (health check `/health`), access logs → logs bucket.
- `modules/cloudfront/`: distribution with ALB origin + custom secret header; ALB listener rule rejects requests missing the header.
- `modules/ecs_service/` (reusable for api + worker): task definition with awslogs driver, task+execution role wiring, secrets injected via `secrets` block from Secrets Manager ARNs, `deployment_circuit_breaker { enable = true, rollback = true }`, service autoscaling on CPU + SQS depth (worker).

### Phase 5 — CI/CD (Week E)
- `.github/workflows/ci.yml`: lint (ruff, terraform fmt, tflint), unit tests, build image, trivy scan, push to ECR tagged with commit SHA on `main`.
- `terraform-plan.yml`: on PR, OIDC assume role, `terraform plan` for dev, post plan as PR comment.
- `deploy-dev.yml`: on push to `main`, apply dev, update ECS service with new image, run smoke tests against ALB DNS.
- `deploy-prod.yml`: manual dispatch, `environment: production` (GitHub protection rule requires approval), apply prod.
- No static AWS keys in GitHub — OIDC only.

### Phase 6 — Observability + reliability (Week E-F)
- `modules/cloudwatch/`: log groups (retention 14d dev / 30d prod), metric filters, dashboards (API health, queue/worker health, DB health, partner integration, business alerts/hr), alarms:
  - API 5xx > 1% for 5 min
  - API p95 > 500ms for 10 min
  - SQS `ApproximateNumberOfMessagesVisible` > N for 10 min
  - DLQ `ApproximateNumberOfMessages` > 0 (immediate)
  - ECS running < desired
  - Partner failure rate burst
  - RDS connection pressure
- `modules/cloudtrail/`: multi-region trail → logs bucket, management events.
- ADOT collector sidecar (or managed) shipping traces to X-Ray; trace context propagated via SQS message attributes (`traceparent`).
- Runbooks written: deployment, rollback, partner outage, queue backlog, DB access issue.

### Phase 7 — Incident simulations + docs (Week F)
Execute and document all three:
1. **Queue backlog explosion** — throttle worker, watch alarm fire, scale out, drain.
2. **Partner API outage** — flip mock-partner to 500s, show retries/backoff/circuit breaker, redrive strategy after recovery.
3. **Bad deployment** — ship broken image, show ECS circuit breaker rollback.
4. **Poison message** — send malformed event, show DLQ fill, fix parser, redrive.

Write one full postmortem from incident #3 into `docs/postmortems/`.

Also ship ADR-003 (least privilege tightening story: start permissive, use IAM Access Analyzer, commit the diff).

---

## Critical files to create

| Path | Purpose |
|---|---|
| `apps/api/app/main.py` | FastAPI app, route definitions, OTel init |
| `apps/api/app/queue_sqs.py` | SQS send with trace propagation |
| `apps/api/app/storage_s3.py` | Partitioned raw event write |
| `apps/worker/worker/main.py` | Long-poll loop, visibility extension |
| `apps/worker/worker/processor.py` | Rule engine |
| `apps/worker/worker/partner_client.py` | Retries, HMAC, circuit breaker, idempotency |
| `apps/worker/worker/dedupe.py` | Postgres-backed idempotency |
| `infra/bootstrap/main.tf` | tfstate bucket, KMS, GitHub OIDC role |
| `infra/modules/network/main.tf` | VPC, subnets, NAT, SGs |
| `infra/modules/vpc_endpoints/main.tf` | S3 gateway + interface endpoints |
| `infra/modules/iam/main.tf` | Task roles with least-privilege policies |
| `infra/modules/ecs_service/main.tf` | Fargate task def + service with circuit breaker rollback |
| `infra/modules/sqs/main.tf` | Main + DLQ + redrive policy |
| `infra/modules/rds/main.tf` | Encrypted Postgres, private, SG-scoped |
| `infra/modules/cloudwatch/main.tf` | Log groups, dashboards, alarms |
| `infra/modules/cloudfront/main.tf` | Distribution with custom header → ALB |
| `infra/envs/dev/main.tf` | Wires modules, S3 backend |
| `.github/workflows/deploy-dev.yml` | OIDC + apply + smoke |
| `local/docker-compose.yml` | api, worker, localstack, postgres, mock-partner |
| `docs/architecture/overview.md` | Diagram + traffic flow + security boundaries |
| `docs/runbooks/*.md` | 5 runbooks |
| `docs/postmortems/2026-*.md` | One real simulated incident writeup |

---

## Verification / success criteria

**Local (Phase 1 exit):**
- `docker compose up` boots clean
- `curl -X POST localhost:8000/events -d @sample.json` → 202 + `event_id`
- Worker log shows event processed within 2s
- Postgres has alert row; mock-partner log shows signed outbound request
- Duplicate POST with same `Idempotency-Key` does not create duplicate alert (dedupe test)

**Dev AWS (Phase 4 exit):**
- `terraform -chdir=infra/envs/dev apply` succeeds from clean state
- ALB DNS returns 200 on `/health`; ECS tasks show healthy in target group
- RDS not reachable from public internet (verify with external curl)
- Secrets never appear in `terraform show` or plan output
- `aws iam simulate-principal-policy` confirms task role can't access unrelated resources

**CI/CD (Phase 5 exit):**
- PR produces terraform plan comment
- Merge to main auto-deploys dev + runs smoke test
- Prod deploy requires approval click in GitHub Environments UI
- Broken image deploy auto-rolls-back via circuit breaker (verify with Phase 7 incident #3)

**Observability (Phase 6 exit):**
- CloudWatch dashboards render with real data
- Alarms can be triggered by load test
- CloudWatch Logs Insights query finds request by `trace_id`
- X-Ray trace shows API → SQS → worker → partner span chain

**Docs (Phase 7 exit):**
- README explains system, local bootstrap, deploy in <5 min reading
- 4 ADRs, 5 runbooks, 1 postmortem present
- Every architecture decision defensible verbally in interview

---

## Cost guardrails

- Tear down dev nightly: `terraform destroy` or stop ECS services + stop RDS (keeps VPC/NAT).
- 1 NAT Gateway in dev, not 2.
- RDS `db.t4g.micro` in dev, Multi-AZ off.
- Log retention 14d in dev.
- VPC endpoints reduce NAT data processing for ECR/S3/Secrets/Logs traffic (real $ savings + interview story).
- Estimated dev idle cost with everything on: ~$50-70/mo. With nightly teardown of RDS+ECS: ~$20-30/mo (VPC + NAT fixed).

## Out of scope (explicitly)
- EKS, Kafka/MSK, Aurora, RDS Proxy, multi-account, service mesh, WAF (mention as upgrade path in ADRs only).
- Staging environment (dev + prod only).
- ML-based anomaly detection (rule-based only).
