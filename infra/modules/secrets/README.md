# infra/modules/secrets

Secrets Manager entries for application-level secrets:

- `${name_prefix}/hmac-signing-key` — randomly generated at apply time (48 chars, safe special set). Used by the worker's partner client to HMAC-sign outbound bodies for Slack/PagerDuty.
- `${name_prefix}/slack-webhook-url` — Slack incoming-webhook URL. Supplied via `var.slack_webhook_url`, defaults to a placeholder so the module is applicable without real credentials on hand.
- `${name_prefix}/pagerduty-routing-key` — PagerDuty Events API v2 routing key. Same pattern as Slack.

## What this module does NOT own

The **RDS master password** is managed by RDS itself via `manage_master_user_password = true` on the `aws_db_instance`. That secret's ARN is surfaced by the `rds` module and passed to the `iam` module separately. Rationale:

- RDS-managed secrets rotate automatically without a separate Lambda.
- The secret is populated atomically with the instance — no race between Terraform creating a secret and RDS referencing it.
- One fewer thing to hand-manage.

## Rotation Lambda (deferred)

The plan calls for a rotation Lambda on the HMAC signing key. It is deferred because:

1. Rotating the HMAC key means coordinating with the mock/real partner so both sides flip at the same instant — otherwise in-flight deliveries fail. That coordination is non-trivial and Phase 3 has no compute deployed to test it.
2. A manual `terraform apply` to regenerate `random_password.hmac_signing_key` (by changing a trigger or tainting the resource) is sufficient for dev. Prod would add a Lambda later.

The HMAC secret has `recovery_window_in_days = 0` by default so dev teardown is clean. Override to 7-30 in prod.

## Access

Access is granted by the `iam` module via the `secret_arns` variable. Pass `module.secrets.all_secret_arns` from the env root so every app-level secret is readable by the task execution role (for env injection) and the task role (for runtime fetch if needed).
