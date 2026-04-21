#
# Bootstrap — one-time setup that creates the dependencies the rest of the
# Terraform tree needs before it can run: the remote state bucket, the KMS key
# that encrypts it, and the GitHub OIDC role CI assumes.
#
# This root uses local state (see versions.tf — no backend block). After a
# successful `terraform apply` here, the dev/prod envs use the S3 bucket
# created below for their remote state.
#

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# --------------------------------------------------------------------------- #
#  KMS key for state bucket encryption
# --------------------------------------------------------------------------- #

resource "aws_kms_key" "tfstate" {
  description             = "Encrypts Terraform state for ${var.name_prefix}"
  enable_key_rotation     = true
  deletion_window_in_days = 14

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowRootAccountAdmin"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "tfstate" {
  name          = "alias/${var.name_prefix}-tfstate"
  target_key_id = aws_kms_key.tfstate.id
}

# --------------------------------------------------------------------------- #
#  S3 bucket for Terraform remote state
# --------------------------------------------------------------------------- #

resource "aws_s3_bucket" "tfstate" {
  bucket = var.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.tfstate.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --------------------------------------------------------------------------- #
#  GitHub OIDC provider + CI role
# --------------------------------------------------------------------------- #

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  # Expand `repo:*:...` wildcards with the actual repo so CI can only assume
  # this role from the configured GitHub repository.
  expanded_allowed_subs = [
    for sub in var.github_allowed_refs : replace(sub, "repo:*:", "repo:${var.github_repository}:")
  ]
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.expanded_allowed_subs
    }
  }
}

resource "aws_iam_role" "github_oidc" {
  name               = "${var.name_prefix}-github-oidc"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
  description        = "Assumed by GitHub Actions via OIDC for ${var.github_repository}"
}

# CI needs to read/write tfstate and invoke KMS on it; everything else is
# granted by per-env policies on the environment root modules.
data "aws_iam_policy_document" "github_tfstate" {
  statement {
    sid    = "StateBucketReadWrite"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketVersioning",
    ]
    resources = [
      aws_s3_bucket.tfstate.arn,
      "${aws_s3_bucket.tfstate.arn}/*",
    ]
  }

  statement {
    sid    = "StateKmsUse"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.tfstate.arn]
  }
}

resource "aws_iam_role_policy" "github_tfstate" {
  name   = "tfstate-access"
  role   = aws_iam_role.github_oidc.id
  policy = data.aws_iam_policy_document.github_tfstate.json
}

# Broad admin policy for dev environment so CI can plan/apply infra changes.
# In prod this would be narrowed to the exact resources the plan touches.
resource "aws_iam_role_policy_attachment" "github_poweruser" {
  role       = aws_iam_role.github_oidc.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy_attachment" "github_iam" {
  role       = aws_iam_role.github_oidc.name
  policy_arn = "arn:aws:iam::aws:policy/IAMFullAccess"
}
