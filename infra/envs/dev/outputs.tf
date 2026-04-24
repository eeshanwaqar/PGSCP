output "vpc_id" {
  value = module.network.vpc_id
}

output "private_app_subnet_ids" {
  value = module.network.private_app_subnet_ids
}

output "private_data_subnet_ids" {
  value = module.network.private_data_subnet_ids
}

output "raw_bucket_name" {
  value = module.s3.raw_bucket_name
}

output "logs_bucket_name" {
  value = module.s3.logs_bucket_name
}

output "app_kms_key_arn" {
  value = module.s3.app_kms_key_arn
}

# --------------------------------------------------------------------------- #
#  IAM
# --------------------------------------------------------------------------- #

output "api_task_role_arn" {
  value = module.iam.api_task_role_arn
}

output "worker_task_role_arn" {
  value = module.iam.worker_task_role_arn
}

output "investigator_task_role_arn" {
  value = module.iam.investigator_task_role_arn
}

output "task_execution_role_arn" {
  value = module.iam.task_execution_role_arn
}

# --------------------------------------------------------------------------- #
#  Secrets (ARNs only — never the values)
# --------------------------------------------------------------------------- #

output "hmac_signing_key_arn" {
  value = module.secrets.hmac_signing_key_arn
}

output "slack_webhook_url_arn" {
  value = module.secrets.slack_webhook_url_arn
}

output "pagerduty_routing_key_arn" {
  value = module.secrets.pagerduty_routing_key_arn
}

# --------------------------------------------------------------------------- #
#  Queues
# --------------------------------------------------------------------------- #

output "events_queue_url" {
  value = module.sqs_events.queue_url
}

output "events_queue_arn" {
  value = module.sqs_events.queue_arn
}

output "events_dlq_url" {
  value = module.sqs_events.dlq_url
}

output "investigations_queue_url" {
  value = module.sqs_investigations.queue_url
}

output "investigations_queue_arn" {
  value = module.sqs_investigations.queue_arn
}

output "investigations_dlq_url" {
  value = module.sqs_investigations.dlq_url
}

# --------------------------------------------------------------------------- #
#  RDS
# --------------------------------------------------------------------------- #

output "db_endpoint" {
  value = module.rds.db_instance_endpoint
}

output "db_port" {
  value = module.rds.db_instance_port
}

output "db_name" {
  value = module.rds.db_name
}

output "db_master_user_secret_arn" {
  description = "RDS-managed Secrets Manager entry holding the master credentials."
  value       = module.rds.master_user_secret_arn
}

# --------------------------------------------------------------------------- #
#  ALB (Phase 4 slice 3)
# --------------------------------------------------------------------------- #

output "alb_dns_name" {
  description = "Public DNS of the ingestion ALB. `curl http://<value>/health` to smoke-test."
  value       = module.alb.alb_dns_name
}

output "alb_url" {
  description = "Full URL for convenience."
  value       = "http://${module.alb.alb_dns_name}"
}
