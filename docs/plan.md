# PGSCP — Production-Grade Secure Cloud Platform

## Status (2026-04-27)

The substance of the project is shipped. Verified end-to-end on real AWS:
a single `curl` to a public ALB exercises ingestion → S3 → SQS → worker rule
engine → Postgres → SQS → LangGraph investigator → reports + Slack delivery.

| Phase | Status | Evidence |
|---|---|---|
| 0 — Repo foundation | ✅ | commit `0265179` |
| 1 — App services, local-first | ✅ | commit `a219fae`; verified end-to-end |
| 2 — TF bootstrap + network + shared | ✅ | commits `dd23853`/`d421ff2`; applied + destroyed cleanly |
| 3 — Data + secrets + queue | ✅ | same commits as Phase 2 |
| 4 — Compute + traffic (ECS, ALB, all 3 services) | ✅ | commits `481e86a`/`3078491`/`55e8d2b`; public `curl` verified |
| 5 — CI/CD | 🟡 slice 1 of 4 | commit `aa71d9b`/`51f030d`; `terraform-plan` workflow green on PR |
| 6 — Observability + reliability | ❌ deferred | — |
| 7 — Incident simulations + 1 postmortem | ❌ deferred | — |
| 7.5 — Interview defense + compliance docs | 🟡 partial | `docs/defense-notes.md` + ADRs 0003/0004 done; OWASP/ISO mappings deferred |
| 8 — LangGraph investigator (added mid-flight) | ✅ | commit `a219fae`; verified on AWS |
| Bonus — Streamlit dashboard | ✅ | commit `1e74513` |

**Deliberate cuts:** Phase 5 slices 2-4 (image-build/apply/deploy CI),
Phase 6 OTel/X-Ray, Phase 7 multi-incident sim, OWASP/ISO mappings.
See [README.md](../README.md) for the rationale.

---

## Context

Portfolio project to prove Cloud Engineer ownership end-to-end: AWS infra via Terraform, secure CI/CD, IAM least-privilege, observability, reliability, incident response. Two blueprints reviewed (Cloud Engineer Project Blueprint + PGSCP). PGSCP is the authoritative design; this plan synthesizes both into an executable build order.

**System shape:** `POST /events` → FastAPI (ECS Fargate) → S3 (raw payload) + SQS → Worker (ECS Fargate) → rules → RDS Postgres + outbound partner API (with retries / idempotency / circuit breaker), DLQ for poison messages, CloudWatch + CloudTrail for ops/audit.

## Domain: LLM Evaluation & Regression-Detection Platform

PGSCP ingests **LLM inference records** from client applications and evaluates them in near-real-time for quality/cost/safety regressions. This domain is chosen because it directly reinforces the CV narrative (LLM systems, evaluation framework, cost optimization, latency reduction, production incidents) without turning PGSCP into an LLM application — PGSCP never calls an LLM itself, it only evaluates traffic someone else generated.

**Client shape:** a service running LLM calls (email classifier, chatbot, agent) POSTs one record per inference to `POST /events`. PGSCP validates, archives the raw record to S3, enqueues for evaluation. The worker runs a rule engine; when a rule fires, an alert is created and notifications go to Slack + PagerDuty.

### Inference record schema (v1)

| Field | Type | Notes |
|---|---|---|
| `schema_version` | string | `"v1"` |
| `request_id` | string | Client-provided or generated |
| `timestamp` | ISO-8601 | When the LLM call happened |
| `model` | string | e.g. `gpt-4o`, `claude-sonnet-4-5`, `llama-3.1-70b` |
| `provider` | string | `openai`, `anthropic`, `bedrock`, `self-hosted` |
| `prompt` | string | Full prompt (hashed if >8KB) |
| `completion` | string | Full completion |
| `prompt_tokens` | int |  |
| `completion_tokens` | int |  |
| `latency_ms` | int |  |
| `cost_usd` | float |  |
| `temperature` | float? |  |
| `user_id` / `session_id` | string? | Upstream identity |
| `expected_label` / `predicted_label` | string? | Present when caller has ground truth |
| `tags` | dict | Free-form metadata |

### Rule engine (worker)

Same rule *shapes* as the generic blueprint, renamed to LLM-native concerns. Keeps architecture unchanged; only names and schemas differ.

| Rule | LLM meaning | Shape reused from blueprint |
|---|---|---|
| `LatencyBreach` | `latency_ms > threshold` per model | hard threshold |
| `CostAnomaly` | cost/call deviates from rolling baseline by >X% | rate-of-change |
| `AccuracyDrift` | rolling accuracy drops below threshold (when `expected_label` is present) | rate-of-change |
| `StuckModel` | `predicted_label` unchanged across last N records for a model | stuck sensor |
| `MissingHeartbeat` | no records for a model in N minutes | missing heartbeat |
| `PiiLeak` | regex detection of emails/phones/cards in `completion` | out-of-range for mode |
| `ToxicityHeuristic` | keyword/regex stand-in — defensible placeholder where prod would plug in a real classifier | out-of-range for mode |

### Alert outputs → partner integrations

Alerts are written to Postgres (`alerts`, `alert_events`, `partner_delivery_attempts`) and delivered to:

- **Slack incoming webhook** — HMAC-signed body for replay protection, retries with backoff, circuit breaker
- **PagerDuty Events API v2** — high-severity regressions only

Both are "the external partner API" from the PGSCP blueprint — unchanged patterns, different wire format.

### Why this domain is interview-defensible

- Mirrors CV bullet *"Introduced evaluation framework using 2,500+ labelled samples for regression detection"* — this repo **is** that system.
- Mirrors *"Influenced LLM costs by 35% through optimization"* — the `CostAnomaly` rule + S3 raw archive is literally how you'd detect and attribute cost drift.
- Mirrors *"Scaled system to 5,000+ daily voice interactions with 99.7% uptime"* — SQS-decoupled architecture is why ingestion stays alive when evaluators slow down.
- Keeps PGSCP firmly in **cloud engineering** scope — no model training, no inference, no GPUs. The AI flavor lives in schemas and rule names, not in infrastructure.

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
  local/
    mock-partner/     tiny FastAPI app simulating Slack/PagerDuty webhooks with tunable failure modes
  docs/
    architecture/overview.md
    decisions/         ADRs: ECS-vs-EKS, SQS-vs-Kafka, Terraform-vs-CF, SQS-vs-Kinesis
    runbooks/          deploy, rollback, partner-outage, queue-backlog, db-issue
    postmortems/       template.md + one real simulated incident
    interview/         defense-notes.md, cost-optimization.md, latency-optimization.md
    compliance/        owasp-top-10.md, iso-27001-mapping.md
    blueprints/        source blueprints (added in Phase 0)
  README.md SECURITY.md
```

---

## Implementation phases

### Phase 0 — Repo foundation (½ day) ✅ shipped
- `git init`, create tree above, `.gitignore`, `.editorconfig`, `pre-commit` (ruff, terraform fmt, tflint, gitleaks).
- README stub with architecture diagram placeholder.
- ADR template + write ADR-001 (ECS vs EKS), ADR-002 (SQS vs Kafka).

### Phase 1 — App services, local-first (Week A–B) ✅ shipped

**API (`apps/api`)** — FastAPI
- Endpoints:
  - `POST /events` — accepts an `InferenceRecord` (LLM eval domain schema, v1), generates `event_id` if absent, returns `202` with `event_id` + `trace_id`.
  - `GET /alerts` — query by `model`, `rule`, `status`, time range.
  - `GET /health` — liveness (process up).
  - `GET /ready` — readiness; checks SQS + Secrets Manager reachability.
  - `GET /metrics` — Prometheus format (or EMF logs for CloudWatch).
- `schemas.py`: Pydantic v2 models — `InferenceRecord` (request body), `IngestResponse`, `Alert`, `AlertEvent`. Enforce `schema_version="v1"` literal; reject `prompt`/`completion` > 32KB with 413.
- `storage_s3.py`: boto3 write to `raw/model=<model>/dt=<YYYY-MM-DD>/<event_id>.json`; SSE-KMS; returns S3 key.
- `queue_sqs.py`: send message with `event_id`, S3 key, `model`, `timestamp`, `schema_version`, `idempotency_key`, `traceparent` attribute for OTel propagation.
- `settings.py`: pydantic-settings, env-driven, never reads secrets from disk. Reads boto3 endpoint overrides for LocalStack.
- `observability.py`: structlog JSON logger with correlation IDs (`trace_id`, `request_id`, `event_id`, `model`); OTel FastAPI auto-instrumentation when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

**Worker (`apps/worker`)**
- Long-poll loop (`WaitTimeSeconds=20`); visibility timeout > max processing time.
- `processor.py`: rule engine with the seven LLM rules above. Each rule is a small class with `evaluate(record, context) -> RuleResult`. Rule context includes rolling stats from Postgres (last N records per model).
- `dedupe.py`: Postgres unique constraint on `idempotency_key` (handles SQS at-least-once). First-writer-wins; duplicates log and no-op.
- `partner_client.py`: httpx with connect=1s/total=5s, exponential backoff + jitter, circuit breaker (`pybreaker`), HMAC signing over body+timestamp, `partner_request_id` idempotency header. Two concrete clients: `SlackWebhookClient`, `PagerDutyClient` — both share base retry/CB behavior.
- `db.py`: SQLAlchemy models for `inference_records` (metadata only — raw stays in S3), `alerts`, `alert_events` (immutable transitions), `partner_delivery_attempts`.
- Alembic migrations for all four tables.

**Local (`local/`)**
- `docker-compose.yml` services: `api`, `worker`, `localstack` (SQS + S3 + Secrets Manager), `postgres`, `mock-partner`, `otel-collector` (optional, behind profile).
- `mock-partner/main.py`: tiny FastAPI app with endpoints `/slack/webhook` and `/pagerduty/v2/enqueue`. Configurable via env: `FAILURE_MODE=none|500|timeout|slow`, `FAILURE_RATE=0.0-1.0`. Logs every received request with signature verification.
- `sample-events/` directory with 5–10 example inference records covering happy path, latency breach, PII leak, cost anomaly, missing heartbeat edge.
- `init.sql` for initial Postgres schema (Alembic runs on worker startup but init.sql is the fallback for fast dev loops).

**Exit criteria for Phase 1**:
- `docker compose up --build` boots clean
- `curl -X POST localhost:8000/events -H 'Idempotency-Key: t1' -d @sample-events/happy.json` → 202 + `event_id`
- Worker log shows evaluation within 2s, no rules fire for happy case
- `curl @sample-events/latency-breach.json` → `LatencyBreach` alert appears in Postgres and mock-partner receives a signed Slack-shaped POST
- Duplicate POST with same `Idempotency-Key` does not create duplicate alert
- PII-leak sample triggers `PiiLeak` rule; cost-anomaly sample triggers `CostAnomaly`

**Tests**: unit tests for each rule, dedupe, partner client retry/CB. Integration test using LocalStack SQS + a throwaway Postgres.

### Phase 2 — Terraform bootstrap + network + shared (Week C start) ✅ shipped
- `infra/bootstrap/`: S3 tfstate bucket (versioning, SSE-KMS, public access block), KMS key, IAM OIDC provider for GitHub, `pgscp-github-oidc` role scoped to repo/branch.
- `modules/network/`: VPC, 2 AZs, public + private-app + private-data subnets, IGW, 1 NAT (dev) / 2 NAT (prod), route tables, security groups (alb-sg, api-sg, worker-sg, rds-sg with SG-to-SG rules only).
- `modules/vpc_endpoints/`: S3 gateway + interface endpoints for ECR api/dkr, Secrets Manager, CloudWatch Logs, SQS.
- `modules/s3/`: `pgscp-raw-events-<env>`, `pgscp-logs-<env>`; SSE-KMS, versioning, lifecycle to Glacier after 30d on raw bucket, block-public-access.
- `modules/iam/`: ECS task execution role (pull ECR, write logs), API task role (s3:PutObject scoped to raw prefix, sqs:SendMessage scoped to queue ARN, secretsmanager:GetSecretValue scoped to `pgscp/*`), worker task role (sqs consume, s3 get, secrets get, rds connect via secret).

### Phase 3 — Data + secrets + queue (Week C end) ✅ shipped
- `modules/secrets/`: Secrets Manager entries for db creds (with rotation Lambda stub), partner API key, HMAC signing secret.
- `modules/rds/`: Postgres 16, encrypted (KMS), not publicly accessible, private data subnet group, SG allows only from worker-sg and api-sg, Multi-AZ=false in dev / true in prod, 7-day backups.
- `modules/sqs/`: main queue + DLQ with `maxReceiveCount=5`, KMS encryption, long-polling defaults.

### Phase 4 — Compute + traffic (Week D) ✅ shipped (slices 1-4: ECR, ECS cluster, worker, API+ALB, investigator)
- `modules/ecr/`: two repos (`api`, `worker`), immutable tags, scan-on-push.
- `modules/alb/`: ALB in public subnets, HTTPS listener with ACM cert, target group for API (health check `/health`), access logs → logs bucket.
- `modules/cloudfront/`: distribution with ALB origin + custom secret header; ALB listener rule rejects requests missing the header.
- `modules/ecs_service/` (reusable for api + worker): task definition with awslogs driver, task+execution role wiring, secrets injected via `secrets` block from Secrets Manager ARNs, `deployment_circuit_breaker { enable = true, rollback = true }`, service autoscaling on CPU + SQS depth (worker).

### Phase 5 — CI/CD (Week E) 🟡 slice 1 of 4 (terraform-plan on PR shipped; image-build/apply/deploy slices deferred)
- `.github/workflows/ci.yml`: lint (ruff, terraform fmt, tflint), unit tests, build image, trivy scan, push to ECR tagged with commit SHA on `main`.
- `terraform-plan.yml`: on PR, OIDC assume role, `terraform plan` for dev, post plan as PR comment.
- `deploy-dev.yml`: on push to `main`, apply dev, update ECS service with new image, run smoke tests against ALB DNS.
- `deploy-prod.yml`: manual dispatch, `environment: production` (GitHub protection rule requires approval), apply prod.
- No static AWS keys in GitHub — OIDC only.

### Phase 6 — Observability + reliability (Week E-F) ❌ deferred
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

### Phase 7 — Incident simulations + docs (Week F) ❌ deferred
Execute and document all four:
1. **Queue backlog explosion** — throttle worker, watch alarm fire, scale out, drain.
2. **Partner API outage** — flip mock-partner (Slack) to 500s, show retries/backoff/circuit breaker, redrive strategy after recovery.
3. **Bad deployment** — ship broken image, show ECS deployment circuit breaker rollback.
4. **Poison inference record** — send malformed event, show DLQ fill, fix parser, redrive.

**Postmortem framing** — incident #1 is written up as the canonical postmortem, deliberately framed as *"synchronous evaluation bottleneck under load → re-architected into SQS-decoupled pipeline"* to mirror the CV proposal narrative: sync coupling caused latency spikes, decoupling via queue restored availability, observability was hardened afterwards.

Also ship ADR-0005 (least-privilege tightening story: start permissive, iteratively narrow using IAM Access Analyzer, commit the diffs as evidence of the process).

### Phase 7.5 — Interview defense + compliance docs (½ day, concurrent with Phase 7) 🟡 partial (defense-notes + ADRs 0003/0004 done; OWASP/ISO mappings deferred)

These are cheap but high-leverage — they convert the repo into direct interview ammunition.

- `docs/interview/defense-notes.md` — one-row-per-claim table mapping each proposal claim (end-to-end AWS ownership, cost optimization 35%, incident response, secure partner integration, OWASP/ISO alignment) to concrete repo artifacts (file paths, ADR numbers, runbook links, dashboard IDs once deployed).
- `docs/interview/cost-optimization.md` — before/after cost breakdown grounded in actual PGSCP levers: NAT data-processing charges avoided via VPC endpoints, SQS-depth autoscaling vs always-on workers, S3 lifecycle to Glacier, right-sized Fargate task sizes, log retention tuned per env. Includes a rough "$/month × 12 months" table that's believable because every number comes from a real AWS pricing page.
- `docs/interview/latency-optimization.md` — the "1.2s → 380ms"-style narrative, reshaped: initial design had the worker synchronously writing to RDS in the `POST /events` critical path, p95 was poor under load; moving the write to the async worker behind SQS restored p95. This is the technical story behind ADR-0002 and it *is* the postmortem from Phase 7 incident #1.
- `docs/compliance/owasp-top-10.md` — control mapping against OWASP Top 10 (2021) with evidence pointers into the repo. Covers A01 access control, A02 crypto failures, A03 injection, A05 security misconfig, A07 auth failures, A08 integrity failures, A09 logging/monitoring, A10 SSRF.
- `docs/compliance/iso-27001-mapping.md` — mapping against ISO/IEC 27001:2022 Annex A themes (A.5 organizational, A.8 technological) with a focus on access control, cryptography, operations security, communications security, supplier relationships (= partner integrations), and incident management. Honest framing: "aligned with, not certified by" — this is the exact wording from the CV.
- `docs/decisions/0003-terraform-over-cloudformation.md` — short ADR naming the TF-over-CF decision (acknowledges CV mentions CloudFormation at NETSOL; defends the move to Terraform as the current industry default).
- `docs/decisions/0004-sqs-vs-kinesis-flink.md` — short ADR naming when each primitive is right (SQS for durable async buffering to a single consumer; Kinesis/Flink for multi-consumer replay and windowed analytics). Defends the CV's mention of Kinesis/Flink at Graph8 as a different tool for a different job.

---

## Critical files to create

| Path | Purpose |
|---|---|
| `apps/api/app/main.py` | FastAPI app, route definitions, OTel init |
| `apps/api/app/schemas.py` | `InferenceRecord` v1 + response models |
| `apps/api/app/queue_sqs.py` | SQS send with trace propagation |
| `apps/api/app/storage_s3.py` | Partitioned raw event write (`raw/model=/dt=/event_id.json`) |
| `apps/worker/worker/main.py` | Long-poll loop, visibility extension |
| `apps/worker/worker/processor.py` | Rule engine (7 LLM rules) |
| `apps/worker/worker/partner_client.py` | Base retries/HMAC/CB; Slack + PagerDuty clients |
| `apps/worker/worker/dedupe.py` | Postgres-backed idempotency |
| `apps/worker/worker/db.py` | SQLAlchemy models + session factory |
| `local/mock-partner/main.py` | Slack + PagerDuty mock with tunable failure modes |
| `local/sample-events/*.json` | Happy path + edge cases (latency, PII, cost, etc.) |
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
| `docs/postmortems/2026-*.md` | Canonical postmortem (sync→async migration story) |
| `docs/interview/defense-notes.md` | Proposal claim → repo artifact map |
| `docs/interview/cost-optimization.md` | Before/after cost breakdown, levers, $ impact |
| `docs/interview/latency-optimization.md` | Sync→async migration narrative, p95 before/after |
| `docs/compliance/owasp-top-10.md` | OWASP Top 10 (2021) control mapping |
| `docs/compliance/iso-27001-mapping.md` | ISO 27001:2022 Annex A mapping |
| `docs/decisions/0003-terraform-over-cloudformation.md` | TF-vs-CF ADR |
| `docs/decisions/0004-sqs-vs-kinesis-flink.md` | SQS-vs-streaming ADR |

---

## Verification / success criteria

**Local (Phase 1 exit):**
- `docker compose up --build` boots clean
- `curl -X POST localhost:8000/events -H 'Idempotency-Key: t1' -d @sample-events/happy.json` → 202 + `event_id`
- Worker log shows evaluation within 2s; no rules fire for happy case
- `sample-events/latency-breach.json` triggers `LatencyBreach` alert → mock-partner receives signed Slack-shaped POST
- `sample-events/pii-leak.json` triggers `PiiLeak`; `cost-anomaly.json` triggers `CostAnomaly`
- Duplicate POST with same `Idempotency-Key` does not create duplicate alert
- Unit tests for all 7 rules pass; integration test against LocalStack SQS passes

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
