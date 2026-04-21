#
# Remote state — points at the S3 bucket + KMS key created by infra/bootstrap.
# Values here are intentionally literals, not variables, because Terraform
# evaluates the backend block before variable interpolation. Update this file
# after the first `bootstrap` apply if the bucket name is different.
#
# Override at init time:
#   terraform init \
#     -backend-config="bucket=<state-bucket-name>" \
#     -backend-config="kms_key_id=<state-kms-key-arn>"
#
terraform {
  backend "s3" {
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
