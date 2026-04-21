#
# Dev environment root — wires all modules shipped so far.
#
# Phase 2: network, vpc_endpoints, s3, iam
# Phase 3: secrets, sqs (events + investigations), rds  ← added in this commit
# Phase 4+: ecr, alb, cloudfront, ecs_service, cloudwatch, cloudtrail
#

module "network" {
  source = "../../modules/network"

  name_prefix        = var.name_prefix
  env                = "dev"
  availability_zones = var.availability_zones
  nat_gateway_count  = 1
}

module "vpc_endpoints" {
  source = "../../modules/vpc_endpoints"

  name_prefix            = var.name_prefix
  vpc_id                 = module.network.vpc_id
  aws_region             = var.aws_region
  private_app_subnet_ids = module.network.private_app_subnet_ids
  private_route_table_ids = concat(
    module.network.private_app_route_table_ids,
    [module.network.private_data_route_table_id],
  )
  security_group_ids      = [module.network.vpc_endpoints_security_group_id]
  enable_bedrock_endpoint = true
}

module "s3" {
  source = "../../modules/s3"

  name_prefix      = var.name_prefix
  env              = "dev"
  raw_bucket_name  = var.raw_bucket_name
  logs_bucket_name = var.logs_bucket_name

  raw_glacier_transition_days = 30
  raw_expiration_days         = 180
}

# --------------------------------------------------------------------------- #
#  Phase 3
# --------------------------------------------------------------------------- #

module "secrets" {
  source = "../../modules/secrets"

  name_prefix           = var.name_prefix
  env                   = "dev"
  app_kms_key_arn       = module.s3.app_kms_key_arn
  slack_webhook_url     = var.slack_webhook_url
  pagerduty_routing_key = var.pagerduty_routing_key
  recovery_window_days  = 0
}

module "sqs_events" {
  source = "../../modules/sqs"

  name_prefix                = var.name_prefix
  queue_name                 = "events"
  kms_key_arn                = module.s3.app_kms_key_arn
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600 # 4 days
  dlq_max_receive_count      = 5
}

module "sqs_investigations" {
  source = "../../modules/sqs"

  name_prefix                = var.name_prefix
  queue_name                 = "investigations"
  kms_key_arn                = module.s3.app_kms_key_arn
  visibility_timeout_seconds = 180 # agent runs can take longer than worker rules
  message_retention_seconds  = 345600
  dlq_max_receive_count      = 5
}

module "rds" {
  source = "../../modules/rds"

  name_prefix             = var.name_prefix
  env                     = "dev"
  private_data_subnet_ids = module.network.private_data_subnet_ids
  rds_security_group_id   = module.network.rds_security_group_id
  app_kms_key_arn         = module.s3.app_kms_key_arn

  instance_class        = var.db_instance_class
  multi_az              = var.db_multi_az
  deletion_protection   = var.db_deletion_protection
  skip_final_snapshot   = true
  backup_retention_days = 7
}

# --------------------------------------------------------------------------- #
#  IAM — re-wired with real ARNs
# --------------------------------------------------------------------------- #

module "iam" {
  source = "../../modules/iam"

  name_prefix     = var.name_prefix
  env             = "dev"
  aws_region      = var.aws_region
  raw_bucket_arn  = module.s3.raw_bucket_arn
  app_kms_key_arn = module.s3.app_kms_key_arn

  events_queue_arn         = module.sqs_events.queue_arn
  investigations_queue_arn = module.sqs_investigations.queue_arn

  # App-level secrets + the RDS-managed master credential. The task execution
  # role needs all of these so ECS can inject them into container env at task
  # start.
  secret_arns = concat(
    module.secrets.all_secret_arns,
    [module.rds.master_user_secret_arn],
  )

  # Phase 6 populates these; investigator's log-query policy stays empty for now.
  api_log_group_arn          = ""
  worker_log_group_arn       = ""
  investigator_log_group_arn = ""
}
