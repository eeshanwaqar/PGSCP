provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project    = "pgscp"
      Component  = "bootstrap"
      ManagedBy  = "terraform"
      Repository = var.github_repository
    }
  }
}
