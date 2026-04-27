# PGSCP — Production-Grade Secure Cloud Platform

> **Datadog for LLMs that investigates itself.**
> Ingest every LLM inference, detect the anomalies traditional observability is blind to (cost spikes, accuracy drift, PII leakage, stuck classifiers), and when something critical fires, an autonomous LangGraph agent gathers evidence, forms hypotheses, and drafts a postmortem — before you wake up.

Built as a portfolio project demonstrating end-to-end ownership of an AI/ML platform: infrastructure-as-code on AWS, CI/CD, secure-by-default services, an LLM agent with deterministic tools, and a CI-gated eval harness with a human feedback loop.

---

## The problem

Traditional monitoring (Datadog, Grafana, NewRelic) is **blind to LLM-specific failure modes**:
- A model is suddenly costing 3× what it did yesterday because of silent prompt expansion
- A classifier is "stuck" returning the same label to every input
- A regex would have caught the email address that leaked into a customer's chat reply
- Accuracy on labelled cases dropped from 92% → 71% after the last prompt change
- This new latency spike correlates with an ECS deploy 12 minutes ago

These need **domain-aware rules** over inference payloads, **and** an agent that understands LLM-operation semantics. PGSCP provides both.

## Architecture

Two coupled planes, both running on AWS ECS Fargate:

```
                        ┌────────────────────────────────────────────────┐
   POST /events  ──►   │                INFERENCE PLANE                  │
                        │                                                │
                        │   FastAPI  ──► S3 (raw, SSE-KMS)               │
                        │      │     ──► SQS events queue                │
                        │      ▼                                         │
                        │   Worker (SQS long-poll)                       │
                        │      │  • dedupe via Postgres uniq             │
                        │      │  • 7 LLM-aware rules:                   │
                        │      │      LatencyBreach · CostAnomaly        │
                        │      │      AccuracyDrift · StuckModel         │
                        │      │      MissingHeartbeat · PiiLeak         │
                        │      │      ToxicityHeuristic                  │
                        │      ├──► Postgres (alerts + audit)            │
                        │      ├──► Slack/PagerDuty (HMAC, retry, CB)    │
                        │      └──► SQS investigations queue (critical)  │
                        └─────────────────────┬──────────────────────────┘
                                              │
                        ┌─────────────────────▼──────────────────────────┐
                        │                CONTROL PLANE                   │
                        │                                                │
                        │   Investigator (LangGraph StateGraph, 6 nodes) │
                        │      receive_alert → gather_context            │
                        │              │                                 │
                        │              │  ◄── 4 deterministic tools:     │
                        │              │       db, s3, cloudwatch, ecs   │
                        │              ▼                                 │
                        │      hypothesize ◄── LLM (scripted/Bedrock     │
                        │              │       /OpenAI-compatible)       │
                        │              ▼                                 │
                        │      [conf ≥ 0.7 or loops ≥ 2 ?]                │
                        │         yes ↓        no → verify → loop        │
                        │      draft_postmortem → deliver                │
                        │              ├──► Postgres `investigations`    │
                        │              └──► Slack                        │
                        │                                                │
                        │   Feedback API (FastAPI :8100)                 │
                        │      POST /investigations/{id}/feedback        │
                        │      → stages regression JSON for next         │
                        │        golden-set PR (CI auto-bumps eval)      │
                        └────────────────────────────────────────────────┘
                                              │
                        ┌─────────────────────▼──────────────────────────┐
                        │      EVAL HARNESS (CI-gated)                   │
                        │      golden.jsonl → 5 metrics:                 │
                        │      RCA · evidence-precision · tool-eff       │
                        │      · cost · p95 latency                      │
                        │      LLM-as-judge for unlabelled cases         │
                        └────────────────────────────────────────────────┘
```

A **Streamlit dashboard** (`apps/dashboard/`) reads from Postgres and the feedback API to render a human view of every alert and every investigation, including the full LangGraph trace.

## What's actually built

| Pillar | Status | Evidence |
|---|---|---|
| Inference plane (API + Worker + 7 rules) | ✅ Local + AWS verified | [`apps/api/`](apps/api/), [`apps/worker/`](apps/worker/) |
| LangGraph investigator (6 nodes, 4 tools, 3 LLM backends) | ✅ Local + AWS verified | [`apps/investigator/`](apps/investigator/) |
| CI-gated eval harness (5 metrics + LLM-as-judge) | ✅ Runs against 10-case `golden.jsonl` | [`apps/investigator/eval/`](apps/investigator/eval/) |
| Feedback loop (regression PR auto-staging) | ✅ Wired end-to-end | [`apps/investigator/investigator/feedback.py`](apps/investigator/investigator/feedback.py) |
| Streamlit observation/feedback UI | ✅ 3 pages, live against local Postgres | [`apps/dashboard/`](apps/dashboard/) |
| AWS infra (12 Terraform modules, full dev env) | ✅ Applied + destroyed cleanly multiple times | [`infra/`](infra/) |
| ECS Fargate deployment (3 services, ALB) | ✅ Public `curl` returns 202 from real ALB | [`infra/modules/ecs_service/`](infra/modules/ecs_service/), [`infra/modules/alb/`](infra/modules/alb/) |
| CI/CD (terraform-plan on PR via GitHub OIDC) | ✅ Workflow green, no static AWS creds | [`.github/workflows/terraform-plan.yml`](.github/workflows/terraform-plan.yml) |
| Architecture decision records | 4 ADRs (ECS vs EKS, SQS vs Kafka, TF vs CFN, SQS vs Kinesis) | [`docs/decisions/`](docs/decisions/) |

## What's deliberately not built

- **Phase 5 slices 2-4** (image-build, apply, deploy CI workflows) — slice 1 already proves the OIDC + GitHub Actions story
- **Phase 6 OTel/X-Ray traces** — structlog + CloudWatch is enough at this scope
- **OWASP / ISO 27001 mappings** — relevant for compliance roles, not for this audience
- **Multi-region / DR** — out of portfolio scope

These are tracked as known cuts in [`docs/plan.md`](docs/plan.md), not bugs.

## Run locally

Prereqs: Docker Desktop.

```bash
cd local
docker compose up -d --build

# Open http://localhost:8501  ← the dashboard
# Open http://localhost:8000/health  ← the API

# Generate traffic — payload is crafted to trip 3 rules
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id": "demo-1",
    "timestamp": "2026-04-25T12:00:00Z",
    "model": "claude-sonnet-4-5",
    "provider": "anthropic",
    "prompt": "What is observability for LLM apps?",
    "completion": "Monitoring tuned to LLM failures. Email demo@example.com.",
    "prompt_tokens": 12, "completion_tokens": 25,
    "latency_ms": 6500, "cost_usd": 1.25
  }'
```

Within 5 seconds the dashboard shows: 3 alerts, 2 investigations, the full LangGraph trace for each.

The local stack runs:

| Service | Port | Purpose |
|---|---|---|
| `api` | 8000 | FastAPI ingestion endpoint |
| `worker` | — | SQS consumer + rule engine |
| `investigator` | 8100 | LangGraph agent + feedback API |
| **`dashboard`** | **8501** | **Streamlit UI** |
| `postgres` | 5432 | Alerts + investigations storage |
| `localstack` | 4566 | Local AWS emulation (S3, SQS, Secrets) |
| `mock-partner` | 9000 | Slack/PagerDuty webhook receiver |

## Deploy to AWS

See [`infra/README.md`](infra/README.md). One-time bootstrap, then `terraform apply` in `envs/dev/` brings up the full Fargate stack (~5 min). End-to-end verified: a `curl` to the public ALB triggers API → S3 → SQS → worker → RDS → SQS → investigator → reports.

CI is GitHub-Actions-driven with OIDC — **no static AWS credentials in the repo**. Every PR touching `infra/**` gets an auto-commented `terraform plan`.

## Repo layout

| Path | Contents |
|---|---|
| `apps/api/` | FastAPI ingestion service |
| `apps/worker/` | SQS consumer, rule engine, partner client |
| `apps/investigator/` | LangGraph investigator + eval harness + feedback API |
| `apps/dashboard/` | Streamlit UI (alerts, investigations, feedback) |
| `infra/bootstrap/` | One-time: tfstate bucket, KMS, GitHub OIDC role |
| `infra/modules/` | 12 reusable Terraform modules |
| `infra/envs/dev-shared/` | Long-lived: ECR repos (persists across teardowns) |
| `infra/envs/dev/` | Ephemeral: full app stack (spin up / destroy per session) |
| `.github/workflows/` | CI/CD via OIDC |
| `local/` | docker-compose for local development |
| `docs/` | Plan, ADRs, blueprints, runbooks, defense notes |

## Where to read further

| If you want to understand... | Read |
|---|---|
| **What this project is and why it exists** | [`docs/blueprints/pgscp.md`](docs/blueprints/pgscp.md) |
| **How each phase was implemented** | [`docs/plan.md`](docs/plan.md) |
| **Why Fargate not EKS, SQS not Kafka, etc.** | [`docs/decisions/`](docs/decisions/) |
| **CV claim → concrete artifact mapping** | [`docs/defense-notes.md`](docs/defense-notes.md) |
| **AWS layout + cost** | [`infra/README.md`](infra/README.md) |
| **Security posture** | [`SECURITY.md`](SECURITY.md) |

## License & status

Portfolio project — single-author, single-account dev environment. The substance is fully working but it is not a hardened multi-tenant product.
