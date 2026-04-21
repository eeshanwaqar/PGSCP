#
# ECR — private container registries for each service.
#
# Long-lived by design. The ephemeral dev environment (envs/dev) can be
# destroyed without losing images, so re-spinning up the stack does not
# require rebuilding + re-pushing every container.
#
# Cost: empty repos are free. Storage is $0.10/GB/month. Data transfer to
# ECS tasks inside the same region is free.
#

resource "aws_ecr_repository" "this" {
  for_each = toset(var.repositories)

  name                 = "${var.name_prefix}-${each.key}"
  image_tag_mutability = var.image_tag_mutability

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Component = "ecr"
    Service   = each.key
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last ${var.image_retention_count} tagged images."
        selection = {
          tagStatus     = "tagged"
          tagPatternList = ["*"]
          countType     = "imageCountMoreThan"
          countNumber   = var.image_retention_count
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after ${var.untagged_expiry_days} day(s)."
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_expiry_days
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
