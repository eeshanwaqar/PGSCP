#
# RDS Postgres 16.
#
# Design decisions:
#   - `manage_master_user_password = true` — RDS generates + rotates the master
#     credential, storing it in Secrets Manager under an AWS-managed name. No
#     rotation Lambda to maintain, and no race between Terraform and RDS on
#     the initial password.
#   - Private data subnet group with no public accessibility. SG allows 5432
#     only from api/worker/investigator SGs (enforced upstream in the network
#     module).
#   - Storage + Performance Insights both encrypted with the app KMS key.
#   - Parameter group sets a few defaults that help observability under load.
#

resource "aws_db_subnet_group" "this" {
  name        = "${var.name_prefix}-db-subnets"
  description = "Private data subnets for ${var.name_prefix} Postgres"
  subnet_ids  = var.private_data_subnet_ids

  tags = {
    Name = "${var.name_prefix}-db-subnets"
  }
}

resource "aws_db_parameter_group" "this" {
  name        = "${var.name_prefix}-pg16"
  family      = "postgres16"
  description = "${var.name_prefix} tunables"

  parameter {
    name  = "log_min_duration_statement"
    value = "500"
  }

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  parameter {
    name  = "log_lock_waits"
    value = "1"
  }

  tags = {
    Name = "${var.name_prefix}-pg16"
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-pg"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  db_name  = var.db_name
  username = var.master_username

  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.app_kms_key_arn

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.app_kms_key_arn

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.rds_security_group_id]
  publicly_accessible    = false
  multi_az               = var.multi_az
  port                   = 5432

  parameter_group_name = aws_db_parameter_group.this.name

  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:30-sun:05:30"

  performance_insights_enabled          = true
  performance_insights_kms_key_id       = var.app_kms_key_arn
  performance_insights_retention_period = var.performance_insights_retention_days

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name_prefix}-pg-final-${formatdate("YYYYMMDDhhmm", timestamp())}"

  auto_minor_version_upgrade = true
  apply_immediately          = true

  tags = {
    Name = "${var.name_prefix}-pg"
    Env  = var.env
  }

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}
