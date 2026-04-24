#
# Dev environment root — wires all modules shipped so far.
#
# Phase 2: network, vpc_endpoints, s3, iam
# Phase 3: secrets, sqs (events + investigations), rds
# Phase 4 slice 2: ecs_cluster, ecs_service_worker (reads image from dev-shared)
# Phase 4 slice 3: alb, ecs_service_api (public ingestion endpoint)
# Phase 4 slice 4: ecs_service_investigator (LangGraph investigator + feedback endpoint)
# Phase 4+: cloudfront, cloudwatch, cloudtrail
#

# Long-lived resources (ECR) live in the dev-shared state, read-only here.
data "terraform_remote_state" "dev_shared" {
  backend = "s3"
  config = {
    bucket = "pgscp-tfstate-830101142420"
    key    = "envs/dev-shared/terraform.tfstate"
    region = var.aws_region
  }
}

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

# --------------------------------------------------------------------------- #
#  Phase 4 slice 2 — ECS cluster + worker service
# --------------------------------------------------------------------------- #

module "ecs_cluster" {
  source = "../../modules/ecs_cluster"

  name_prefix = var.name_prefix
}

module "ecs_service_worker" {
  source = "../../modules/ecs_service"

  name_prefix  = var.name_prefix
  service_name = "worker"
  aws_region   = var.aws_region
  cluster_id   = module.ecs_cluster.cluster_id

  image         = "${data.terraform_remote_state.dev_shared.outputs.ecr_repository_urls.worker}:latest"
  cpu           = 256
  memory        = 512
  desired_count = 1

  task_role_arn      = module.iam.worker_task_role_arn
  execution_role_arn = module.iam.task_execution_role_arn

  subnet_ids         = module.network.private_app_subnet_ids
  security_group_ids = [module.network.worker_security_group_id]
  assign_public_ip   = false

  environment = {
    PGSCP_ENV                       = "dev"
    PGSCP_AWS_REGION                = var.aws_region
    PGSCP_S3_RAW_BUCKET             = module.s3.raw_bucket_name
    PGSCP_SQS_QUEUE_URL             = module.sqs_events.queue_url
    PGSCP_INVESTIGATIONS_QUEUE_URL  = module.sqs_investigations.queue_url
    PGSCP_DB_HOST                   = module.rds.db_instance_address
    PGSCP_DB_PORT                   = tostring(module.rds.db_instance_port)
    PGSCP_DB_NAME                   = module.rds.db_name
    PGSCP_LOG_LEVEL                 = "INFO"
    # Partner delivery disabled in dev-AWS (no mock-partner here). Worker
    # still evaluates rules and writes alerts to Postgres; partner rows
    # simply are not created.
    PGSCP_SLACK_WEBHOOK_URL = ""
    PGSCP_PAGERDUTY_URL     = ""
  }

  # Secrets injected at task start. Values here are ARNs; `arn:::username::`
  # extracts the `username` JSON field from the RDS-managed master secret.
  secrets = {
    PGSCP_DB_USER         = "${module.rds.master_user_secret_arn}:username::"
    PGSCP_DB_PASSWORD     = "${module.rds.master_user_secret_arn}:password::"
    PGSCP_HMAC_SIGNING_KEY = module.secrets.hmac_signing_key_arn
  }

  log_retention_days     = 7
  enable_execute_command = false
}

# --------------------------------------------------------------------------- #
#  Phase 4 slice 3 -- ALB + API service
# --------------------------------------------------------------------------- #

module "alb" {
  source = "../../modules/alb"

  name_prefix        = var.name_prefix
  vpc_id             = module.network.vpc_id
  public_subnet_ids  = module.network.public_subnet_ids
  security_group_ids = [module.network.alb_security_group_id]

  target_port       = 8000
  listener_port     = 80
  listener_protocol = "HTTP"
  health_check_path = "/health"
}

module "ecs_service_api" {
  source = "../../modules/ecs_service"

  name_prefix  = var.name_prefix
  service_name = "api"
  aws_region   = var.aws_region
  cluster_id   = module.ecs_cluster.cluster_id

  image         = "${data.terraform_remote_state.dev_shared.outputs.ecr_repository_urls.api}:latest"
  cpu           = 256
  memory        = 512
  desired_count = 1

  task_role_arn      = module.iam.api_task_role_arn
  execution_role_arn = module.iam.task_execution_role_arn

  subnet_ids         = module.network.private_app_subnet_ids
  security_group_ids = [module.network.api_security_group_id]
  assign_public_ip   = false

  container_port = 8000

  load_balancer = {
    target_group_arn = module.alb.target_group_arn
    container_name   = "api"
    container_port   = 8000
  }

  environment = {
    PGSCP_ENV           = "dev"
    PGSCP_AWS_REGION    = var.aws_region
    PGSCP_S3_RAW_BUCKET = module.s3.raw_bucket_name
    PGSCP_SQS_QUEUE_URL = module.sqs_events.queue_url
    PGSCP_LOG_LEVEL     = "INFO"
  }

  # API reads no secrets at runtime -- the sensitive data (HMAC signing key,
  # partner creds) is only needed by the worker.
  secrets = {}

  log_retention_days     = 7
  enable_execute_command = false

  health_check_command = [
    "CMD-SHELL",
    "python -c 'import urllib.request,sys; sys.exit(0 if urllib.request.urlopen(\"http://127.0.0.1:8000/health\", timeout=2).status==200 else 1)'",
  ]
}

# --------------------------------------------------------------------------- #
#  Phase 4 slice 4 -- Investigator service
# --------------------------------------------------------------------------- #

module "ecs_service_investigator" {
  source = "../../modules/ecs_service"

  name_prefix  = var.name_prefix
  service_name = "investigator"
  aws_region   = var.aws_region
  cluster_id   = module.ecs_cluster.cluster_id

  image         = "${data.terraform_remote_state.dev_shared.outputs.ecr_repository_urls.investigator}:latest"
  cpu           = 512
  memory        = 1024
  desired_count = 1

  task_role_arn      = module.iam.investigator_task_role_arn
  execution_role_arn = module.iam.task_execution_role_arn

  subnet_ids         = module.network.private_app_subnet_ids
  security_group_ids = [module.network.investigator_security_group_id]
  assign_public_ip   = false

  # Feedback server is internal-only for now; no ALB exposure. Container
  # still binds 8100 for in-VPC reachability.
  container_port = 0

  environment = {
    PGSCP_ENV                      = "dev"
    PGSCP_AWS_REGION               = var.aws_region
    PGSCP_S3_RAW_BUCKET            = module.s3.raw_bucket_name
    PGSCP_INVESTIGATIONS_QUEUE_URL = module.sqs_investigations.queue_url
    PGSCP_DB_HOST                  = module.rds.db_instance_address
    PGSCP_DB_PORT                  = tostring(module.rds.db_instance_port)
    PGSCP_DB_NAME                  = module.rds.db_name
    PGSCP_LOG_LEVEL                = "INFO"
    # Deterministic scripted LLM backend keeps slice 4 free of Bedrock model
    # approval + API costs. Switch to `bedrock` in a later phase.
    PGSCP_LLM_BACKEND              = "scripted"
    PGSCP_CLOUDWATCH_API_LOG_GROUP    = "/pgscp/${var.name_prefix}/api"
    PGSCP_CLOUDWATCH_WORKER_LOG_GROUP = "/pgscp/${var.name_prefix}/worker"
    PGSCP_ECS_CLUSTER                 = module.ecs_cluster.cluster_name
    PGSCP_GRAPH_VERIFY_MAX_LOOPS      = "2"
    PGSCP_GRAPH_CONFIDENCE_THRESHOLD  = "0.7"
    PGSCP_FEEDBACK_PORT               = "8100"
  }

  secrets = {
    PGSCP_DB_USER           = "${module.rds.master_user_secret_arn}:username::"
    PGSCP_DB_PASSWORD       = "${module.rds.master_user_secret_arn}:password::"
    PGSCP_SLACK_WEBHOOK_URL = module.secrets.slack_webhook_url_arn
    PGSCP_HMAC_SIGNING_KEY  = module.secrets.hmac_signing_key_arn
  }

  log_retention_days     = 7
  enable_execute_command = false
}
