#
# Security groups - SG-to-SG references only, no CIDRs except for the public
# ALB which must accept HTTPS from the internet.
#
# Shape:
#   alb_sg      - public HTTPS toALB
#   api_sg      - ALB to API    (container port)
#   worker_sg   - egress only; receives no inbound traffic
#   rds_sg      - api_sg + worker_sg to RDS on db_port
#   vpc_endpoints_sg - api_sg + worker_sg to interface endpoints on 443
#

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "ALB - public HTTPS in, API egress out"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-alb-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "Public HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "alb_all" {
  security_group_id = aws_security_group.alb.id
  description       = "ALB may reach API targets"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# --------------------------------------------------------------------------- #

resource "aws_security_group" "api" {
  name        = "${var.name_prefix}-api-sg"
  description = "API task - receives ALB traffic, talks to AWS APIs"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-api-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "api_from_alb" {
  security_group_id            = aws_security_group.api.id
  description                  = "ALB to API container port"
  ip_protocol                  = "tcp"
  from_port                    = var.api_container_port
  to_port                      = var.api_container_port
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_egress_rule" "api_all" {
  security_group_id = aws_security_group.api.id
  description       = "API egress (S3, SQS, Secrets, RDS, partner API via NAT)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# --------------------------------------------------------------------------- #

resource "aws_security_group" "worker" {
  name        = "${var.name_prefix}-worker-sg"
  description = "Worker task - no inbound; egress to AWS APIs + partner"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-worker-sg"
  }
}

resource "aws_vpc_security_group_egress_rule" "worker_all" {
  security_group_id = aws_security_group.worker.id
  description       = "Worker egress"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# --------------------------------------------------------------------------- #

resource "aws_security_group" "investigator" {
  name        = "${var.name_prefix}-investigator-sg"
  description = "Investigator task - no inbound from internet; feedback port from VPC only"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-investigator-sg"
  }
}

resource "aws_vpc_security_group_egress_rule" "investigator_all" {
  security_group_id = aws_security_group.investigator.id
  description       = "Investigator egress (Bedrock, S3, SQS, RDS, CW logs)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# --------------------------------------------------------------------------- #

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "RDS - accepts DB traffic from api/worker/investigator only"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-rds-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_api" {
  security_group_id            = aws_security_group.rds.id
  description                  = "API to RDS"
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  referenced_security_group_id = aws_security_group.api.id
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_worker" {
  security_group_id            = aws_security_group.rds.id
  description                  = "Worker to RDS"
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  referenced_security_group_id = aws_security_group.worker.id
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_investigator" {
  security_group_id            = aws_security_group.rds.id
  description                  = "Investigator to RDS"
  ip_protocol                  = "tcp"
  from_port                    = var.db_port
  to_port                      = var.db_port
  referenced_security_group_id = aws_security_group.investigator.id
}

# --------------------------------------------------------------------------- #

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}-vpc-endpoints-sg"
  description = "Interface endpoints - 443 from app tasks"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-vpc-endpoints-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_api" {
  security_group_id            = aws_security_group.vpc_endpoints.id
  description                  = "API to interface endpoint 443"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.api.id
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_worker" {
  security_group_id            = aws_security_group.vpc_endpoints.id
  description                  = "Worker to interface endpoint 443"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.worker.id
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_investigator" {
  security_group_id            = aws_security_group.vpc_endpoints.id
  description                  = "Investigator to interface endpoint 443"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.investigator.id
}
