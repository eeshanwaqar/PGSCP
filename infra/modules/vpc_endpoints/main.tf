#
# VPC endpoints — keep AWS API traffic on the AWS backbone instead of going
# through NAT. Savings are both operational (no NAT data processing charges for
# these services) and defensible security-wise (traffic never leaves the VPC).
#
#   S3          — gateway endpoint (no ENI, no hourly charge)
#   ECR API+DKR — interface endpoints (image pulls)
#   Secrets     — interface endpoint (db creds, partner key, HMAC key, bedrock cfg)
#   CW Logs     — interface endpoint (task logs without NAT cost)
#   SQS         — interface endpoint (events queue, investigations queue)
#   Bedrock     — interface endpoint (optional; investigator target LLM)
#

# --------------------------------------------------------------------------- #
#  Gateway endpoint — S3
# --------------------------------------------------------------------------- #

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  tags = {
    Name = "${var.name_prefix}-vpce-s3"
  }
}

# --------------------------------------------------------------------------- #
#  Interface endpoints
# --------------------------------------------------------------------------- #

locals {
  interface_services = merge(
    {
      "ecr-api"        = "com.amazonaws.${var.aws_region}.ecr.api"
      "ecr-dkr"        = "com.amazonaws.${var.aws_region}.ecr.dkr"
      "secretsmanager" = "com.amazonaws.${var.aws_region}.secretsmanager"
      "logs"           = "com.amazonaws.${var.aws_region}.logs"
      "sqs"            = "com.amazonaws.${var.aws_region}.sqs"
    },
    var.enable_bedrock_endpoint ? {
      "bedrock-runtime" = "com.amazonaws.${var.aws_region}.bedrock-runtime"
    } : {}
  )
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_services

  vpc_id              = var.vpc_id
  service_name        = each.value
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_app_subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = {
    Name = "${var.name_prefix}-vpce-${each.key}"
  }
}
