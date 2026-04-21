output "ecr_repository_urls" {
  description = "Map of service short name to ECR repository URI, e.g. `api` -> `830101142420.dkr.ecr.us-east-1.amazonaws.com/pgscp-dev-api`."
  value       = module.ecr.repository_urls
}

output "ecr_repository_arns" {
  description = "Map of service short name to ECR repository ARN."
  value       = module.ecr.repository_arns
}

output "ecr_registry_id" {
  description = "Account ID hosting the ECR repositories (used for docker login)."
  value       = module.ecr.registry_id
}
