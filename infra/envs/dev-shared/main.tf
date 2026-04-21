#
# Dev-shared — long-lived resources that persist across envs/dev spin-up/down
# cycles. Container images, and (later) Route53 records or ACM certs.
#
# Apply once. Only destroy when you are done with the project.
#

module "ecr" {
  source = "../../modules/ecr"

  name_prefix           = var.name_prefix
  repositories          = ["api", "worker", "investigator"]
  image_retention_count = 10
  untagged_expiry_days  = 1
}
