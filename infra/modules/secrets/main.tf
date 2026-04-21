#
# App-level secrets.
#
# The RDS master password is NOT managed here — we use `manage_master_user_password`
# on the RDS instance so AWS generates and rotates it for us. That secret's ARN is
# surfaced by the rds module and injected into the task execution role separately.
#
# This module owns the secrets the application itself creates:
#   - HMAC signing key (generated at apply time, rotated by a new `terraform apply`)
#   - Slack webhook URL (supplied via var.slack_webhook_url, placeholder by default)
#   - PagerDuty routing key (supplied via var.pagerduty_routing_key, placeholder by default)
#
# A rotation Lambda stub is documented in README.md for the HMAC key — it is out
# of scope for Phase 3 because Phase-3 compute is not deployed yet.
#

resource "random_password" "hmac_signing_key" {
  length  = 48
  special = true
  # Stick to a safe special set so the secret can be used verbatim in HTTP
  # headers and HMAC computations without escaping.
  override_special = "!#$%^&*()-_=+[]{}"
}

resource "aws_secretsmanager_secret" "hmac_signing_key" {
  name                    = "${var.name_prefix}/hmac-signing-key"
  description             = "HMAC signing key for partner delivery (pgscp ${var.env})"
  kms_key_id              = var.app_kms_key_arn
  recovery_window_in_days = var.recovery_window_days
}

resource "aws_secretsmanager_secret_version" "hmac_signing_key" {
  secret_id     = aws_secretsmanager_secret.hmac_signing_key.id
  secret_string = random_password.hmac_signing_key.result
}

# --------------------------------------------------------------------------- #
#  Slack webhook URL
# --------------------------------------------------------------------------- #

resource "aws_secretsmanager_secret" "slack_webhook_url" {
  name                    = "${var.name_prefix}/slack-webhook-url"
  description             = "Slack incoming-webhook URL (pgscp ${var.env})"
  kms_key_id              = var.app_kms_key_arn
  recovery_window_in_days = var.recovery_window_days
}

resource "aws_secretsmanager_secret_version" "slack_webhook_url" {
  secret_id     = aws_secretsmanager_secret.slack_webhook_url.id
  secret_string = var.slack_webhook_url
}

# --------------------------------------------------------------------------- #
#  PagerDuty routing key
# --------------------------------------------------------------------------- #

resource "aws_secretsmanager_secret" "pagerduty_routing_key" {
  name                    = "${var.name_prefix}/pagerduty-routing-key"
  description             = "PagerDuty Events API v2 routing key (pgscp ${var.env})"
  kms_key_id              = var.app_kms_key_arn
  recovery_window_in_days = var.recovery_window_days
}

resource "aws_secretsmanager_secret_version" "pagerduty_routing_key" {
  secret_id     = aws_secretsmanager_secret.pagerduty_routing_key.id
  secret_string = var.pagerduty_routing_key
}
