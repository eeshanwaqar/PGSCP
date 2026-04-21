variable "name_prefix" {
  type = string
}

variable "env" {
  type = string
}

variable "private_data_subnet_ids" {
  description = "Private data-tier subnets for the DB subnet group."
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "SG applied to the DB instance. Should allow 5432 from api/worker/investigator SGs only."
  type        = string
}

variable "app_kms_key_arn" {
  description = "KMS key for storage + Performance Insights encryption."
  type        = string
}

variable "engine_version" {
  description = "Postgres engine version."
  type        = string
  default     = "16.4"
}

variable "instance_class" {
  description = "DB instance class. Use db.t4g.micro for dev."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Initial storage in GB."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Autoscaling ceiling. Set equal to allocated_storage to disable autoscaling."
  type        = number
  default     = 100
}

variable "db_name" {
  type    = string
  default = "pgscp"
}

variable "master_username" {
  description = "Master username. Password is managed by RDS and stored in Secrets Manager automatically."
  type        = string
  default     = "pgscp_admin"
}

variable "multi_az" {
  description = "Multi-AZ deployment. Off in dev to save cost; on in prod."
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  description = "How many days of automated backups to retain."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Deletion protection. Off in dev so teardown is clean; on in prod."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip the final snapshot when the instance is destroyed. Dev only."
  type        = bool
  default     = true
}

variable "performance_insights_retention_days" {
  description = "Performance Insights retention. 7 = free tier."
  type        = number
  default     = 7
}
