provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "pgscp"
      Env       = "dev-shared"
      ManagedBy = "terraform"
    }
  }
}
