# Defense notes

> The 30-minute pre-interview map. For every claim a recruiter or hiring manager might
> probe, this document points at the concrete file, commit, ADR, runbook, or
> screenshot that proves it. If a claim isn't here, it's not on the CV.

Audience: yourself, the night before an interview. Not for distribution.

---

## How to use this document

Open it in one tab. Open the GitHub repo in another. When asked "tell me about your
AWS work" or "show me the LangGraph piece", the answer is *which file or PR to scroll
to*, not a story you have to remember.

Every row in the tables below has a **link** (relative path) to the artifact and a
1-sentence narrative you can use verbatim.

---

## 1 · Cloud Engineer claims

### "I built and deployed a multi-service application on AWS, infrastructure-as-code"

| Evidence | Where to look | Narrative |
|---|---|---|
| 12 Terraform modules with consistent layout | [`infra/modules/`](../infra/modules/) | "I structured infra around reusable modules — `network`, `iam`, `s3`, `secrets`, `sqs`, `rds`, `vpc_endpoints`, `ecr`, `ecs_cluster`, `ecs_service`, `alb`. Each has its own `main/variables/outputs/versions.tf`." |
| One-time bootstrap separated from per-env state | [`infra/bootstrap/`](../infra/bootstrap/) | "Bootstrap creates the state bucket, KMS key, and GitHub OIDC role. It uses local state because it bootstraps the very bucket everyone else uses for remote state — that chicken-and-egg has a clean solution." |
| Ephemeral vs long-lived envs | [`infra/envs/dev-shared/`](../infra/envs/dev-shared/) vs [`infra/envs/dev/`](../infra/envs/dev/) | "ECR is in `dev-shared` so images survive across `dev` teardowns. Compute + RDS go in `dev` so I can spin up / spin down in 5-7 min and pay pennies per session." |
| Network design with 3-tier subnets, single NAT for cost | [`infra/modules/network/`](../infra/modules/network/) | "Public / private-app / private-data subnets across 2 AZs. NAT count is a variable — 1 in dev, 2 in prod. RDS lives in `private_data` with no egress route." |
| Verified end-to-end on real AWS | Smoke-test transcripts in conversation history | "I `terraform apply`-d four times during build, fixed real-world bugs (SG description ASCII rules, KMS GenerateDataKey gap), then ran a `curl` against the public ALB and watched the message flow API → S3 → SQS → worker → RDS → SQS → investigator." |

### "Production hygiene — idempotency, retries, DLQs, audit trails"

| Evidence | Where to look | Narrative |
|---|---|---|
| Idempotency via Postgres unique constraint | [`apps/worker/worker/db.py`](../apps/worker/worker/db.py) (`InferenceRecordRow.idempotency_key`) | "Each event derives a stable idempotency key. Replays hit the unique constraint → worker logs `duplicate_dropped` and acks the SQS message. No double-processing." |
| Partner delivery with retries + circuit breaker + DLQ | [`apps/worker/worker/partner_client.py`](../apps/worker/worker/partner_client.py) | "HMAC-signed webhooks, exponential backoff, 5 retries, circuit breaker that opens on repeated failure, DLQ after exhaustion. Every attempt recorded in `partner_delivery_attempts`." |
| Append-only alert audit trail | `alert_events` table | "Every alert state transition (created, escalated, resolved) is one row. Never updated, never deleted." |
| SQS DLQ wired in Terraform | [`infra/modules/sqs/main.tf`](../infra/modules/sqs/main.tf) | "Generic queue module instantiated twice (events 60s visibility, investigations 180s). Both have DLQs with `maxReceiveCount=5`." |

### "Security-by-default"

| Evidence | Where to look | Narrative |
|---|---|---|
| KMS-encrypted everything | `s3/main.tf`, `sqs/main.tf`, `rds/main.tf`, `secrets/main.tf` | "App KMS key encrypts the raw events bucket, both SQS queues, the RDS instance, and Secrets Manager entries. Bucket-key enabled where applicable for cost." |
| RDS-managed master password | [`infra/modules/rds/main.tf`](../infra/modules/rds/main.tf) (`manage_master_user_password = true`) | "RDS generates and rotates the master credential. Its Secrets Manager ARN flows into the IAM module's `secret_arns`. ECS injects it into containers at task start via `:username::` / `:password::` JSON-key extraction — no rotation Lambda to maintain." |
| SG-to-SG references, not CIDRs | [`infra/modules/network/security-groups.tf`](../infra/modules/network/security-groups.tf) | "Only the public ALB rule uses `0.0.0.0/0`. Every internal hop is `api-sg → rds-sg`, not a CIDR. Means I can't accidentally expose RDS by widening a subnet." |
| Conditional IAM statements | [`infra/modules/iam/main.tf`](../infra/modules/iam/main.tf) | "Each task role has `dynamic "statement"` blocks gated on whether the dependent ARN exists yet. Avoids an intermediate broken state during phased rollout." |
| GitHub OIDC, no long-lived AWS keys | [`infra/bootstrap/main.tf`](../infra/bootstrap/main.tf) | "CI assumes `pgscp-github-oidc` via `sts:AssumeRoleWithWebIdentity`. Trust policy pins the GitHub repo + allowed refs. There is **no** `AWS_ACCESS_KEY_ID` secret in the repo." |
| Real bugs surfaced + fixed during build | Conversation history (KMS GenerateDataKey, ASCII SG descriptions) | "First `terraform apply` failed three times for legitimate reasons. Fixed each — non-ASCII em-dashes in SG descriptions, `kms:GenerateDataKey` missing on worker for encrypted-SQS sends, `ecs:DescribeServices` missing on investigator." |

### "CI/CD with GitHub Actions"

| Evidence | Where to look | Narrative |
|---|---|---|
| Plan on every PR via OIDC | [`.github/workflows/terraform-plan.yml`](../.github/workflows/terraform-plan.yml) | "`pull_request` trigger on `infra/**` — matrix over `dev-shared` and `dev` roots. `terraform fmt + init + validate + plan`, posts the plan as a PR comment. Bootstrap deliberately excluded (local state)." |
| Honest commit history showing the iteration | `git log` | "I shipped this in slices. Each PR triggered the workflow; the first PR found a real bug (missing tfvars), the next fix made the workflow green." |

### "Cost-aware operations"

| Evidence | Where to look | Narrative |
|---|---|---|
| Spin-up / spin-down cycle, ~$0.40/session | [`infra/README.md#cost`](../infra/README.md) | "Dev costs ~$0.12/hr running. I `apply` at the start of a session, smoke-test, `destroy`, and walk away with $0.30-0.50 burned. Bootstrap is ~$1/mo perpetual." |
| Single NAT in dev, scalable to 2 in prod | [`infra/modules/network/variables.tf`](../infra/modules/network/variables.tf) | "`nat_gateway_count` is a single variable. 1 in dev to save $33/mo, 2 in prod for HA." |
| VPC endpoints to skip NAT data fees | [`infra/modules/vpc_endpoints/`](../infra/modules/vpc_endpoints/) | "Six interface endpoints (ECR x2, Secrets, Logs, SQS, Bedrock) plus the S3 gateway. Saves NAT data-processing for every AWS API call from the app tasks." |
| Lifecycle on raw bucket | [`infra/modules/s3/main.tf`](../infra/modules/s3/main.tf) | "Raw events transition to Glacier after 30 days, expire after 180. Replay window is preserved; long-tail storage is cheap." |

---

## 2 · ML/AI Platform Engineer claims

### "Built a LangGraph agent for incident investigation"

| Evidence | Where to look | Narrative |
|---|---|---|
| 6-node StateGraph | [`apps/investigator/investigator/graph.py`](../apps/investigator/investigator/graph.py) | "`receive_alert → gather_context → hypothesize → (verify-loop or skip) → draft_postmortem → deliver`. Verify loop is bounded by `graph_verify_max_loops=2` and `graph_confidence_threshold=0.7`." |
| Pure-function nodes over typed state | [`apps/investigator/investigator/nodes.py`](../apps/investigator/investigator/nodes.py), [`state.py`](../apps/investigator/investigator/state.py) | "Each node takes the `InvestigationState` TypedDict and returns a delta. Easy to reason about, easy to test in isolation." |
| Pluggable LLM backend | [`apps/investigator/investigator/llm.py`](../apps/investigator/investigator/llm.py) | "Three backends behind one interface: `scripted` (deterministic, $0, used in CI evals), `bedrock` (Claude 3.5 Sonnet, priced per 1M tokens), `openai` (any OpenAI-compatible endpoint). Switched via env var." |
| 4 deterministic tools | [`apps/investigator/investigator/tools/`](../apps/investigator/investigator/tools/) | "`db.py`, `s3.py`, `cloudwatch.py`, `ecs.py`. All deterministic — no random sampling, no vector search. Same alert → same evidence bundle. This is what makes evals reproducible." |

### "CI-gated eval harness with 5 metrics"

| Evidence | Where to look | Narrative |
|---|---|---|
| 10-case golden set | [`apps/investigator/eval/dataset/golden.jsonl`](../apps/investigator/eval/dataset/golden.jsonl) | "Each case is a labelled seed + expected root-cause label. I ran the scripted backend at 70% RCA, 65% evidence precision, $0 cost, 7ms p95." |
| 5 metrics computed per run | [`apps/investigator/eval/metrics.py`](../apps/investigator/eval/metrics.py) | "Root-cause accuracy, evidence precision, tool-call efficiency, mean cost USD, p95 latency. The last two are real numbers from the LLM API." |
| LLM-as-judge for unlabelled cases | [`apps/investigator/eval/judge.py`](../apps/investigator/eval/judge.py) | "5-point rubric — plausibility, evidence consistency, actionability, alternatives, calibration. A second LLM scores the first one's output." |

### "Human feedback loop that auto-grows the regression dataset"

| Evidence | Where to look | Narrative |
|---|---|---|
| Feedback API | [`apps/investigator/investigator/feedback.py`](../apps/investigator/investigator/feedback.py) | "`POST /investigations/{id}/feedback` — when `correct=false`, the case is staged as JSON in `/tmp/pgscp/regressions/{id}.json`." |
| Streamlit UI surfacing the API | [`apps/dashboard/pgscp_dashboard/pages/2_Investigations.py`](../apps/dashboard/pgscp_dashboard/pages/2_Investigations.py) | "Reviewer clicks `incorrect`, types the correct label + notes, hits submit. The dashboard `httpx.post`s to the investigator. Two clicks, no SQL." |
| Designed for a CI Action to PR the staged cases | feedback.py docstring | "A scheduled Action picks up the staged JSON files and opens a PR appending them to `golden.jsonl`. Service stays stateless; dataset changes live in git history." |

### "Observability for LLM operations"

| Evidence | Where to look | Narrative |
|---|---|---|
| 7 LLM-aware rules | [`apps/worker/worker/rules.py`](../apps/worker/worker/rules.py) | "LatencyBreach, CostAnomaly (absolute + rolling-baseline ratio), AccuracyDrift, StuckModel (last-N labels), MissingHeartbeat, PiiLeak (regex for email/phone/CC/SSN), ToxicityHeuristic." |
| Streamlit dashboard showing the LangGraph trace | [`apps/dashboard/`](../apps/dashboard/) | "Every alert and every investigation in one place. Click into an investigation → see the evidence, hypotheses with confidence bars, the verdict, and a feedback button. Read-only on Postgres." |
| Audit trail per alert | `alert_events` + `partner_delivery_attempts` | "Every alert and every Slack/PagerDuty attempt is rowed. Click into an alert in the dashboard → see who got paged when." |

---

## 3 · Things that are *not* on the CV (be honest if asked)

These would be over-claiming until further work lands. If an interviewer asks about them directly, the honest answer is in the right column.

| Topic | Honest answer |
|---|---|
| "How do you do incident simulations?" | "Phase 7 of my plan is incident sims — partner outage, queue backlog, bad deploy, poison record. I scoped the four scenarios in `docs/plan.md` but I haven't run them yet. The infra is ready; I'd write the playbooks in a real role." |
| "How do you handle prod traffic?" | "The dev environment is fully equivalent to prod modulo `prod` having multi-AZ RDS, deletion protection on, and tighter IAM. I designed for that split — `prod/` is a skeleton — but I haven't applied a separate prod stack." |
| "What's your tracing story?" | "Structlog JSON logs with `trace_id` propagation in correlation middleware. CloudWatch Logs Insights queries by `trace_id` work end-to-end. Real OTel/X-Ray instrumentation is out of scope for this iteration — Phase 6." |
| "Compliance — OWASP, ISO, SOC2?" | "Phase 7.5 has placeholders for OWASP Top 10 and ISO 27001 Annex A mappings. They aren't filled in. The technical controls (KMS, IAM least-privilege, audit trails, network segmentation) are there to back any of those frameworks — the mapping is paperwork I'd do in a compliance-leaning role." |
| "Multi-region / DR?" | "Single-region. RDS backups + raw-events S3 versioning give point-in-time recovery within `us-east-1`. Multi-region is out of portfolio scope." |

---

## 4 · The "show me it works" demo flow

If an interviewer says "show me it working":

1. `cd local && docker compose up -d --build` — 3 minutes
2. Open http://localhost:8501 in a second tab
3. Run the `curl` from the README in a third tab
4. Switch to the dashboard, click **Investigations**, pick the latest row
5. Walk them through: evidence → hypotheses → verdict → click "incorrect" → submit feedback → show the staged JSON via `docker exec pgscp-investigator-1 ls /tmp/pgscp/regressions/`

About a 4-minute flow. Practiced once, it's the most concrete demo you can show.

For a longer cut, also do:
- `cd infra/envs/dev && terraform apply -auto-approve` — 5 min wait
- `curl http://<alb-dns>/events ...` — proves it on real AWS
- Show CloudWatch Logs Insights query filtering by `trace_id` across api/worker/investigator
- `terraform destroy` — show the spin-up/spin-down discipline

---

## 5 · The two CV bullets you can defend most strongly

Pick these as your headlines:

1. **"Built and deployed a two-plane LLM observability platform on AWS Fargate, with a LangGraph incident-investigation agent, CI-gated eval harness, and a feedback loop that auto-grows the regression dataset."**
   - Maps to: [`apps/`](../apps/), [`infra/`](../infra/), the conversation transcript of `terraform apply` working end-to-end.

2. **"Designed and shipped 12 Terraform modules + a GitHub OIDC-based CI/CD pipeline with zero static AWS credentials. Verified end-to-end with a public `curl` exercising the full pipeline (API → S3 → SQS → worker → RDS → investigator) on real AWS."**
   - Maps to: [`infra/`](../infra/), [`.github/workflows/`](../.github/workflows/), the smoke-test transcripts.

Everything else is supporting evidence.
