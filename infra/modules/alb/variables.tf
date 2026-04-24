variable "name_prefix" {
  description = "Resource name prefix (e.g. pgscp-dev). ALB name is <name_prefix>-alb."
  type        = string
}

variable "vpc_id" {
  description = "VPC the ALB + target group live in."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets the ALB attaches to. Must be in at least 2 AZs."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups applied to the ALB. Typically the network module's alb_security_group_id."
  type        = list(string)
}

variable "target_port" {
  description = "Port on the target container the ALB forwards traffic to (API listener port)."
  type        = number
  default     = 8000
}

variable "listener_port" {
  description = "Port the ALB listens on for public traffic. 80 for HTTP, 443 for HTTPS."
  type        = number
  default     = 80
}

variable "listener_protocol" {
  description = "HTTP or HTTPS. HTTPS requires certificate_arn."
  type        = string
  default     = "HTTP"
  validation {
    condition     = contains(["HTTP", "HTTPS"], var.listener_protocol)
    error_message = "listener_protocol must be HTTP or HTTPS."
  }
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS listeners. Ignored when listener_protocol is HTTP."
  type        = string
  default     = ""
}

variable "health_check_path" {
  description = "HTTP path the ALB pings on each target to decide if it is healthy."
  type        = string
  default     = "/health"
}

variable "health_check_interval_seconds" {
  description = "How often (seconds) the ALB health-checks each target."
  type        = number
  default     = 30
}

variable "health_check_timeout_seconds" {
  description = "Timeout for each health check."
  type        = number
  default     = 5
}

variable "healthy_threshold" {
  description = "Consecutive successful checks before a target is considered healthy."
  type        = number
  default     = 2
}

variable "unhealthy_threshold" {
  description = "Consecutive failed checks before a target is considered unhealthy."
  type        = number
  default     = 3
}

variable "deregistration_delay_seconds" {
  description = "Seconds the target group waits before deregistering a target. Shorter is faster deploys; longer gives in-flight requests time to finish."
  type        = number
  default     = 30
}

variable "enable_deletion_protection" {
  description = "Prevent accidental `terraform destroy`. Enable in prod, leave off in dev."
  type        = bool
  default     = false
}

variable "idle_timeout_seconds" {
  description = "Seconds an idle connection is held open before being closed."
  type        = number
  default     = 60
}
