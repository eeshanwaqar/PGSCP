variable "name_prefix" {
  type = string
}

variable "env" {
  type = string
}

variable "raw_bucket_name" {
  description = "Bucket for raw inference record archive. Must be globally unique."
  type        = string
}

variable "logs_bucket_name" {
  description = "Bucket for ALB/CloudTrail/access logs. Must be globally unique."
  type        = string
}

variable "raw_glacier_transition_days" {
  description = "Move raw events to Glacier after N days to control cost."
  type        = number
  default     = 30
}

variable "raw_expiration_days" {
  description = "Delete raw events after N days. Dev-only; prod keeps longer retention."
  type        = number
  default     = 365
}
