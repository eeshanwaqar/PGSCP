# Security policy

## Principles

1. **Least privilege.** Every IAM role has a narrow policy scoped to specific resource ARNs. Task roles are per-service (API, worker). No wildcards on `Resource` unless explicitly justified in an ADR.
2. **No secrets in code.** Secrets live in AWS Secrets Manager. They are injected into ECS tasks via the task definition `secrets` block. They never appear in Terraform state, CI variables, environment files in git, or container images.
3. **Private by default.** Only the ALB lives in a public subnet. ECS tasks and RDS are in private subnets. RDS is not publicly accessible and is reachable only from API/worker security groups.
4. **Encryption everywhere.**
   - TLS on the ALB (ACM-managed certificate).
   - SSE-KMS on S3 buckets and RDS storage.
   - Encrypted SQS queues.
   - Encrypted Terraform state bucket.
5. **Auditability.** CloudTrail is enabled for the account. Application logs include correlation IDs (`trace_id`, `request_id`, `event_id`) and are shipped to CloudWatch Logs. All infrastructure changes go through PR review and leave an audit trail in git + GitHub Actions.
6. **Change safety.** Deployments are gated by branch protections, required CI checks, and — for production — GitHub Environments approval rules. Failed deployments auto-roll-back via ECS deployment circuit breaker.

## Secrets inventory

Stored in AWS Secrets Manager under the `pgscp/<env>/` prefix:

| Secret | Used by | Rotation |
|---|---|---|
| `pgscp/<env>/db` | api, worker | Secrets Manager managed rotation (planned) |
| `pgscp/<env>/partner-api-key` | worker | Manual, documented in runbook |
| `pgscp/<env>/hmac-signing-key` | worker | Manual, dual-key rollover |

## Reporting a vulnerability

This is a portfolio project, not a production service. If you are reviewing the repo and spot a security issue, open a GitHub issue with the `security` label.

## Threat model (summary)

| Asset | Threat | Control |
|---|---|---|
| Raw event data (S3) | Unauthorized read | Bucket policy + SSE-KMS + block-public-access |
| Partner API key | Leak via logs or state | Secrets Manager + log scrubbing + Terraform sensitive vars |
| Database | SQL injection, unauthorized network access | Parameterized queries (SQLAlchemy), private subnet, SG allowlist |
| ALB → origin | Direct-to-origin bypass of CloudFront | Custom secret header enforced at ALB listener rule |
| CI/CD | Stolen long-lived AWS keys | GitHub OIDC only — no static access keys |
