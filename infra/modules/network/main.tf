#
# VPC + subnets + routing + NAT.
#
# Three subnet tiers per AZ:
#   - public       → ALB, NAT gateway
#   - private_app  → ECS Fargate tasks (API, worker, investigator)
#   - private_data → RDS Postgres
#
# dev runs a single NAT (cost); prod runs one per AZ (HA). NAT AZ count is
# controlled by var.nat_gateway_count.
#

locals {
  az_count     = length(var.availability_zones)
  public_count = length(var.public_subnet_cidrs)
  app_count    = length(var.private_app_subnet_cidrs)
  data_count   = length(var.private_data_subnet_cidrs)
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.name_prefix}-vpc"
    Env  = var.env
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-igw"
  }
}

# --------------------------------------------------------------------------- #
#  Subnets
# --------------------------------------------------------------------------- #

resource "aws_subnet" "public" {
  count                   = local.public_count
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.name_prefix}-public-${var.availability_zones[count.index]}"
    Tier = "public"
  }
}

resource "aws_subnet" "private_app" {
  count             = local.app_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_app_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "${var.name_prefix}-private-app-${var.availability_zones[count.index]}"
    Tier = "private-app"
  }
}

resource "aws_subnet" "private_data" {
  count             = local.data_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_data_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "${var.name_prefix}-private-data-${var.availability_zones[count.index]}"
    Tier = "private-data"
  }
}

# --------------------------------------------------------------------------- #
#  NAT gateways
# --------------------------------------------------------------------------- #

resource "aws_eip" "nat" {
  count  = var.nat_gateway_count
  domain = "vpc"

  tags = {
    Name = "${var.name_prefix}-nat-eip-${count.index}"
  }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count         = var.nat_gateway_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name = "${var.name_prefix}-nat-${count.index}"
  }

  depends_on = [aws_internet_gateway.this]
}

# --------------------------------------------------------------------------- #
#  Route tables
# --------------------------------------------------------------------------- #

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "${var.name_prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = local.public_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One private route table per NAT gateway. Private subnets in an AZ use the
# NAT in the same AZ when HA is enabled, and fall back to index 0 otherwise.
resource "aws_route_table" "private_app" {
  count  = var.nat_gateway_count
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[count.index].id
  }

  tags = {
    Name = "${var.name_prefix}-private-app-rt-${count.index}"
  }
}

resource "aws_route_table_association" "private_app" {
  count          = local.app_count
  subnet_id      = aws_subnet.private_app[count.index].id
  route_table_id = aws_route_table.private_app[count.index % var.nat_gateway_count].id
}

# Data subnets have no egress — they only talk to the VPC via security groups.
# No NAT route; intentional. VPC endpoints cover the AWS API traffic they need.
resource "aws_route_table" "private_data" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-private-data-rt"
  }
}

resource "aws_route_table_association" "private_data" {
  count          = local.data_count
  subnet_id      = aws_subnet.private_data[count.index].id
  route_table_id = aws_route_table.private_data.id
}
