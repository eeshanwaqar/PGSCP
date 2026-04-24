#
# Application Load Balancer + target group + listener.
#
# Designed for a single backend service (the API). Multi-service routing via
# path/host rules can be layered on top with aws_lb_listener_rule resources
# later.
#
# Target type = ip because Fargate tasks use the awsvpc network mode -- each
# task gets its own ENI that the ALB registers directly by private IP.
#

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = var.security_group_ids
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.enable_deletion_protection
  idle_timeout               = var.idle_timeout_seconds

  # Default is drop_invalid_header_fields = false; turn on for minor hardening.
  drop_invalid_header_fields = true

  tags = {
    Component = "alb"
  }
}

resource "aws_lb_target_group" "this" {
  name        = "${var.name_prefix}-tg"
  vpc_id      = var.vpc_id
  target_type = "ip"
  port        = var.target_port
  protocol    = "HTTP"

  deregistration_delay = var.deregistration_delay_seconds

  health_check {
    enabled             = true
    path                = var.health_check_path
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = var.healthy_threshold
    unhealthy_threshold = var.unhealthy_threshold
    interval            = var.health_check_interval_seconds
    timeout             = var.health_check_timeout_seconds
    matcher             = "200"
  }

  tags = {
    Component = "alb"
  }
}

resource "aws_lb_listener" "this" {
  load_balancer_arn = aws_lb.this.arn
  port              = var.listener_port
  protocol          = var.listener_protocol

  # TLS configuration only applies to HTTPS.
  ssl_policy      = var.listener_protocol == "HTTPS" ? "ELBSecurityPolicy-TLS13-1-2-2021-06" : null
  certificate_arn = var.listener_protocol == "HTTPS" ? var.certificate_arn : null

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }

  tags = {
    Component = "alb"
  }
}
