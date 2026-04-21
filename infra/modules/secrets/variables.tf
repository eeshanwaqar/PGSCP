variable "name_prefix" {
  type = string
}

variable "env" {
  type = string
}

variable "app_kms_key_arn" {
  description = "KMS key used to encrypt secret values."
  type        = string
}

variable "slack_webhook_url" {
  description = "Slack incoming-webhook URL for partner delivery. Write once at apply time; rotate via `terraform apply` with a new value. Use a placeholder locally."
  type        = string
  default     = "http://placeholder.invalid/slack"
  sensitive   = true
}

variable "pagerduty_routing_key" {
  description = "PagerDuty Events API v2 routing key. Placeholder by default; rotate via apply."
  type        = string
  default     = "not-a-real-pagerduty-key"
  sensitive   = true
}

variable "recovery_window_days" {
  description = "Secrets Manager recovery window. 0 = immediate delete on destroy (dev). 7-30 for prod."
  type        = number
  default     = 0
}
