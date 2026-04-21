output "repository_urls" {
  description = "Map of service short name to ECR repository URI (e.g. `api` -> `123.dkr.ecr.us-east-1.amazonaws.com/pgscp-dev-api`). Used for `docker push` and ECS task definitions."
  value       = { for k, v in aws_ecr_repository.this : k => v.repository_url }
}

output "repository_arns" {
  description = "Map of service short name to ECR repository ARN. Used by IAM policies."
  value       = { for k, v in aws_ecr_repository.this : k => v.arn }
}

output "repository_names" {
  description = "Map of service short name to full ECR repository name."
  value       = { for k, v in aws_ecr_repository.this : k => v.name }
}

output "registry_id" {
  description = "Account ID hosting the repositories (same as caller account). Used for ECR docker login."
  value       = values(aws_ecr_repository.this)[0].registry_id
}
