variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "private_app_subnet_ids" {
  description = "Subnet IDs where interface endpoint ENIs are placed."
  type        = list(string)
}

variable "private_route_table_ids" {
  description = "Route table IDs to associate with the S3 gateway endpoint (private_app + private_data)."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups attached to interface endpoints."
  type        = list(string)
}

variable "enable_bedrock_endpoint" {
  description = "Also create a Bedrock runtime interface endpoint so the investigator can reach Bedrock without NAT egress."
  type        = bool
  default     = true
}
