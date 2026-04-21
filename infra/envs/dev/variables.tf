variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "pgscp-dev"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "raw_bucket_name" {
  description = "Globally unique name for the raw events bucket."
  type        = string
}

variable "logs_bucket_name" {
  description = "Globally unique name for the logs bucket."
  type        = string
}

# --------------------------------------------------------------------------- #
#  Phase 3: secrets + data + queues
# --------------------------------------------------------------------------- #

variable "slack_webhook_url" {
  description = "Slack incoming-webhook URL. Placeholder acceptable for initial apply."
  type        = string
  default     = "http://placeholder.invalid/slack"
  sensitive   = true
}

variable "pagerduty_routing_key" {
  description = "PagerDuty Events API v2 routing key. Placeholder acceptable for initial apply."
  type        = string
  default     = "not-a-real-pagerduty-key"
  sensitive   = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}
