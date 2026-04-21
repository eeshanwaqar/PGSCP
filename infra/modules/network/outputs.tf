output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_app_subnet_ids" {
  value = aws_subnet.private_app[*].id
}

output "private_data_subnet_ids" {
  value = aws_subnet.private_data[*].id
}

output "private_app_route_table_ids" {
  value = aws_route_table.private_app[*].id
}

output "private_data_route_table_id" {
  value = aws_route_table.private_data.id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "api_security_group_id" {
  value = aws_security_group.api.id
}

output "worker_security_group_id" {
  value = aws_security_group.worker.id
}

output "investigator_security_group_id" {
  value = aws_security_group.investigator.id
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "vpc_endpoints_security_group_id" {
  value = aws_security_group.vpc_endpoints.id
}
