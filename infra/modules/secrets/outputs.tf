output "hmac_signing_key_arn" {
  value = aws_secretsmanager_secret.hmac_signing_key.arn
}

output "slack_webhook_url_arn" {
  value = aws_secretsmanager_secret.slack_webhook_url.arn
}

output "pagerduty_routing_key_arn" {
  value = aws_secretsmanager_secret.pagerduty_routing_key.arn
}

output "all_secret_arns" {
  description = "List of all app-level secret ARNs — passed to the IAM module so task roles can read them."
  value = [
    aws_secretsmanager_secret.hmac_signing_key.arn,
    aws_secretsmanager_secret.slack_webhook_url.arn,
    aws_secretsmanager_secret.pagerduty_routing_key.arn,
  ]
}
