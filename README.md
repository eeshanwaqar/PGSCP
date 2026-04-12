# PGSCP — Production-Grade Secure Cloud Platform

Real-time event ingestion, asynchronous processing, and alerting platform on AWS. Built as a portfolio project demonstrating end-to-end Cloud Engineer ownership: infrastructure-as-code, CI/CD, security, observability, reliability, and incident response.

## What it does

Partner systems POST events to an API. The API validates, persists raw payloads to S3, and enqueues processing work to SQS. A worker service consumes the queue, applies rule-based anomaly detection, writes alerts to PostgreSQL, and delivers notifications to an external partner API with retries, idempotency, and a circuit breaker.

## Architecture (high level)

```
Client → CloudFront → ALB → ECS Fargate (API) ─┬→ S3 (raw events, SSE-KMS)
                                                └→ SQS ─→ ECS Fargate (Worker) ─┬→ RDS Postgres
                                                            ↓ redrive              ├→ Partner API
                                                           DLQ                     └→ CloudWatch
```

Full details: [docs/architecture/overview.md](docs/architecture/overview.md).

## Repo layout

| Path | Contents |
|---|---|
| `apps/api/` | FastAPI ingestion service |
| `apps/worker/` | SQS consumer, rule engine, partner client |
| `infra/bootstrap/` | One-time Terraform: tfstate bucket, KMS, GitHub OIDC |
| `infra/envs/{dev,prod}/` | Per-environment Terraform root modules |
| `infra/modules/` | Reusable Terraform modules |
| `.github/workflows/` | CI/CD pipelines (OIDC-based) |
| `local/` | docker-compose for local development |
| `docs/architecture/` | System overview, diagrams |
| `docs/decisions/` | Architecture Decision Records |
| `docs/runbooks/` | Operational runbooks |
| `docs/postmortems/` | Incident postmortems |
| `docs/blueprints/` | Source blueprints that shaped this project |
| `docs/plan.md` | Executable implementation plan |

## Run locally

Prereqs: Docker, Docker Compose.

```bash
cd local
docker compose up --build
# API on http://localhost:8000
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: test-1' \
  -d '{"device_id":"sensor-1","timestamp":"2026-04-12T10:00:00Z","value":42.5}'
```

Local stack: API + Worker + LocalStack (SQS/S3/Secrets) + Postgres + mock partner API.

## Deploy (AWS)

See [docs/runbooks/deploy.md](docs/runbooks/deploy.md). CI/CD is GitHub-Actions-driven with OIDC — no static AWS credentials.

## Project status

In active development. See [docs/plan.md](docs/plan.md) for the phased implementation plan and current progress.

## Documentation index

- **Plan**: [docs/plan.md](docs/plan.md)
- **Architecture**: [docs/architecture/overview.md](docs/architecture/overview.md)
- **ADRs**: [docs/decisions/](docs/decisions/)
- **Runbooks**: [docs/runbooks/](docs/runbooks/)
- **Postmortems**: [docs/postmortems/](docs/postmortems/)
- **Source blueprints**: [docs/blueprints/](docs/blueprints/)
- **Security policy**: [SECURITY.md](SECURITY.md)
