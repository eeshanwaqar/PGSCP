#
# Long-lived shared state for dev. Lives in the same state bucket as envs/dev
# but under a different key so it can be applied and destroyed independently.
#
# Override at init time:
#   terraform init \
#     -backend-config="bucket=<state-bucket-name>" \
#     -backend-config="kms_key_id=<state-kms-key-arn>"
#
terraform {
  backend "s3" {
    key          = "envs/dev-shared/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
