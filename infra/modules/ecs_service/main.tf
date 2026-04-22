#
# Generic ECS Fargate service: one CloudWatch log group, one task definition,
# one ECS service. Designed to be instantiated once per app (api, worker,
# investigator).
#
# Design choices:
#   - One container per task. Sidecars can be added later if needed.
#   - awslogs driver. EMF or OTel collectors would go alongside in Phase 6.
#   - No autoscaling here; add via aws_appautoscaling_policy when needed.
#   - execute-command enabled by default for interactive debugging (dev-only).
#

locals {
  full_service_name = "${var.name_prefix}-${var.service_name}"

  # ECS container definition format. Build as a list of maps then jsonencode.
  container_definition = {
    name      = var.service_name
    image     = var.image
    essential = true

    environment = [
      for k, v in var.environment : {
        name  = k
        value = v
      }
    ]

    secrets = [
      for k, v in var.secrets : {
        name      = k
        valueFrom = v
      }
    ]

    portMappings = var.container_port > 0 ? [
      {
        containerPort = var.container_port
        protocol      = "tcp"
      }
    ] : []

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = var.service_name
      }
    }

    healthCheck = length(var.health_check_command) > 0 ? {
      command     = var.health_check_command
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    } : null
  }
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/pgscp/${var.name_prefix}/${var.service_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Component = "ecs_service"
    Service   = var.service_name
  }
}

resource "aws_ecs_task_definition" "this" {
  family                   = local.full_service_name
  cpu                      = var.cpu
  memory                   = var.memory
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]

  task_role_arn      = var.task_role_arn
  execution_role_arn = var.execution_role_arn

  container_definitions = jsonencode([local.container_definition])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  tags = {
    Component = "ecs_service"
    Service   = var.service_name
  }
}

resource "aws_ecs_service" "this" {
  name            = local.full_service_name
  cluster         = var.cluster_id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  enable_execute_command = var.enable_execute_command

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = var.assign_public_ip
  }

  dynamic "load_balancer" {
    for_each = var.load_balancer == null ? [] : [var.load_balancer]
    content {
      target_group_arn = load_balancer.value.target_group_arn
      container_name   = load_balancer.value.container_name
      container_port   = load_balancer.value.container_port
    }
  }

  # Without this, changing the task_def causes ECS to stop old tasks before
  # starting new ones. deployment_minimum_healthy_percent keeps one healthy.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  lifecycle {
    # Desired count can be mutated by autoscaling; ignore so Terraform does
    # not reset it on every apply.
    ignore_changes = [desired_count]
  }

  tags = {
    Component = "ecs_service"
    Service   = var.service_name
  }
}
