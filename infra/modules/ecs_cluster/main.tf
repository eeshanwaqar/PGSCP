#
# ECS Fargate cluster. No EC2 capacity providers -- this is a fully managed
# serverless cluster. Container Insights is enabled by default because the
# cost is small and the visibility on cpu/memory/restart counts is what ECS
# debugging lives on.
#

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  tags = {
    Component = "ecs_cluster"
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}
