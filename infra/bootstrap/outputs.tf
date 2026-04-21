output "state_bucket_name" {
  description = "S3 bucket holding Terraform remote state."
  value       = aws_s3_bucket.tfstate.bucket
}

output "state_bucket_arn" {
  value = aws_s3_bucket.tfstate.arn
}

output "state_kms_key_arn" {
  value = aws_kms_key.tfstate.arn
}

output "state_kms_alias" {
  value = aws_kms_alias.tfstate.name
}

output "github_oidc_role_arn" {
  description = "ARN of the role GitHub Actions assumes via OIDC."
  value       = aws_iam_role.github_oidc.arn
}

output "github_oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}
