variable "aws_region" {
  description = "AWS region for the state bucket and KMS key."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for globally-named resources (S3 buckets)."
  type        = string
  default     = "pgscp"
}

variable "state_bucket_name" {
  description = "Name of the S3 bucket that holds Terraform remote state. Must be globally unique."
  type        = string
}

variable "github_repository" {
  description = "GitHub repo allowed to assume the CI role, in `owner/repo` form."
  type        = string
}

variable "github_allowed_refs" {
  description = "Git refs allowed to assume the CI role (tied into the OIDC trust policy sub condition)."
  type        = list(string)
  default = [
    "repo:*:ref:refs/heads/main",
    "repo:*:pull_request",
    "repo:*:environment:dev",
    "repo:*:environment:production",
  ]
}
