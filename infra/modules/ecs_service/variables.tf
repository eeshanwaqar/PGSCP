variable "name_prefix" {
  description = "Resource name prefix (e.g. pgscp-dev). Service name is <name_prefix>-<service_name>."
  type        = string
}

variable "service_name" {
  description = "Short service name, e.g. api, worker, investigator."
  type        = string
}

variable "cluster_id" {
  description = "ECS cluster ARN to deploy the service into."
  type        = string
}

variable "aws_region" {
  description = "AWS region, used for the awslogs driver."
  type        = string
}

variable "image" {
  description = "Container image URI (e.g. <acct>.dkr.ecr.<region>.amazonaws.com/pgscp-dev-worker:slice2)."
  type        = string
}

variable "cpu" {
  description = "Task CPU in CPU units. 256 = 0.25 vCPU. Must pair with a compatible memory value."
  type        = number
  default     = 256
}

variable "memory" {
  description = "Task memory in MiB. See Fargate cpu/memory combos."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Number of tasks to run."
  type        = number
  default     = 1
}

variable "task_role_arn" {
  description = "IAM role assumed by application code inside the container (SQS, S3, Secrets reads)."
  type        = string
}

variable "execution_role_arn" {
  description = "IAM role used by ECS to pull the image, inject secrets into env, and write logs."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets the tasks run in. Usually the private-app subnets."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups applied to the task ENI."
  type        = list(string)
}

variable "assign_public_ip" {
  description = "Whether the task ENI gets a public IP. False for private subnets."
  type        = bool
  default     = false
}

variable "container_port" {
  description = "Port the container exposes. Set to 0 if the service has no listening port (e.g. worker)."
  type        = number
  default     = 0
}

variable "environment" {
  description = "Plain environment variables passed to the container (not secrets)."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secrets injected as env vars. Map of env var name to Secrets Manager ARN (optionally with :json-key:: suffix)."
  type        = map(string)
  default     = {}
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the task log group."
  type        = number
  default     = 7
}

variable "enable_execute_command" {
  description = "Allow `aws ecs execute-command` for interactive debugging. Requires the task role to have SSM permissions."
  type        = bool
  default     = true
}

variable "load_balancer" {
  description = "Optional ALB target group wiring. Leave null for services that do not sit behind an ALB."
  type = object({
    target_group_arn = string
    container_name   = string
    container_port   = number
  })
  default = null
}

variable "health_check_command" {
  description = "Optional container-level health check. A list of command args, e.g. [\"CMD-SHELL\", \"curl -f http://localhost:8000/health || exit 1\"]."
  type        = list(string)
  default     = []
}
