output "db_instance_id" {
  value = aws_db_instance.this.id
}

output "db_instance_arn" {
  value = aws_db_instance.this.arn
}

output "db_instance_endpoint" {
  value = aws_db_instance.this.endpoint
}

output "db_instance_address" {
  value = aws_db_instance.this.address
}

output "db_instance_port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "master_username" {
  value = aws_db_instance.this.username
}

output "master_user_secret_arn" {
  description = "ARN of the RDS-managed Secrets Manager entry holding the master credentials."
  value       = try(aws_db_instance.this.master_user_secret[0].secret_arn, "")
}
