variable "name_prefix" {
  type = string
}

variable "env" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "raw_bucket_arn" {
  description = "ARN of the raw events S3 bucket. API writes, worker/investigator read."
  type        = string
}

variable "app_kms_key_arn" {
  description = "KMS key that encrypts the raw bucket + secrets."
  type        = string
}

variable "events_queue_arn" {
  description = "ARN of the main events SQS queue. API sends; worker receives."
  type        = string
  default     = ""
}

variable "investigations_queue_arn" {
  description = "ARN of the investigations SQS queue. Worker sends; investigator receives."
  type        = string
  default     = ""
}

variable "secret_arns" {
  description = "List of Secrets Manager ARNs the task roles may read. Accepts both concrete and wildcard ARNs."
  type        = list(string)
  default     = []
}

variable "api_log_group_arn" {
  description = "ARN of the CloudWatch log group the API writes to."
  type        = string
  default     = ""
}

variable "worker_log_group_arn" {
  description = "ARN of the CloudWatch log group the worker writes to."
  type        = string
  default     = ""
}

variable "investigator_log_group_arn" {
  description = "ARN of the CloudWatch log group the investigator writes to."
  type        = string
  default     = ""
}

variable "bedrock_model_arns" {
  description = "Bedrock model ARNs the investigator is allowed to invoke."
  type        = list(string)
  default = [
    "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
    "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-opus-20240229-v1:0",
  ]
}
