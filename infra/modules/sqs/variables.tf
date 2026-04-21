variable "name_prefix" {
  description = "Resource name prefix (e.g. `pgscp-dev`)."
  type        = string
}

variable "queue_name" {
  description = "Short queue suffix (e.g. `events`, `investigations`). Final name is `<name_prefix>-<queue_name>`."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS CMK used for at-rest encryption on the queue."
  type        = string
}

variable "visibility_timeout_seconds" {
  description = "How long a consumed message is invisible to other consumers. Must exceed the worst-case processing time."
  type        = number
  default     = 60
}

variable "message_retention_seconds" {
  description = "How long an undelivered message is kept on the main queue. Max 14 days."
  type        = number
  default     = 345600 # 4 days
  validation {
    condition     = var.message_retention_seconds >= 60 && var.message_retention_seconds <= 1209600
    error_message = "message_retention_seconds must be between 60 and 1209600 (14 days)."
  }
}

variable "receive_wait_time_seconds" {
  description = "Long-poll wait time. 20 is the AWS max and is the only sensible default for workers."
  type        = number
  default     = 20
}

variable "dlq_max_receive_count" {
  description = "Number of unsuccessful receives before a message is moved to the DLQ."
  type        = number
  default     = 5
}

variable "dlq_message_retention_seconds" {
  description = "DLQ retention. Longer than main so operators have time to triage."
  type        = number
  default     = 1209600 # 14 days
}
