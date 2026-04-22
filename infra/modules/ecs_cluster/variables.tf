variable "name_prefix" {
  description = "Resource name prefix (e.g. pgscp-dev). Cluster name is <name_prefix>."
  type        = string
}

variable "enable_container_insights" {
  description = "Turns on CloudWatch Container Insights. Small CW cost; high debugging value in dev."
  type        = bool
  default     = true
}
