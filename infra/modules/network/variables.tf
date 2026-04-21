variable "name_prefix" {
  description = "Prefix applied to all resource names (e.g. `pgscp-dev`)."
  type        = string
}

variable "env" {
  description = "Environment name (`dev`, `prod`)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "availability_zones" {
  description = "AZs to spread subnets across. Must have at least 2."
  type        = list(string)
  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least two availability zones are required."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDRs for public subnets, one per AZ."
  type        = list(string)
  default     = ["10.20.0.0/24", "10.20.1.0/24"]
}

variable "private_app_subnet_cidrs" {
  description = "CIDRs for private application subnets (ECS tasks), one per AZ."
  type        = list(string)
  default     = ["10.20.10.0/24", "10.20.11.0/24"]
}

variable "private_data_subnet_cidrs" {
  description = "CIDRs for private data subnets (RDS), one per AZ."
  type        = list(string)
  default     = ["10.20.20.0/24", "10.20.21.0/24"]
}

variable "nat_gateway_count" {
  description = "Number of NAT gateways to provision. 1 is cheap-enough for dev; 2 gives per-AZ HA for prod."
  type        = number
  default     = 1
  validation {
    condition     = var.nat_gateway_count >= 1 && var.nat_gateway_count <= 2
    error_message = "nat_gateway_count must be 1 or 2."
  }
}

variable "api_container_port" {
  description = "Port the API container listens on behind the ALB."
  type        = number
  default     = 8000
}

variable "db_port" {
  description = "Port the database listens on."
  type        = number
  default     = 5432
}
