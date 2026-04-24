output "alb_arn" {
  description = "ALB ARN."
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "Public DNS of the ALB (e.g. pgscp-dev-alb-123.us-east-1.elb.amazonaws.com). curl this."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Route 53 hosted zone of the ALB. Used for alias records."
  value       = aws_lb.this.zone_id
}

output "target_group_arn" {
  description = "Target group ARN. Pass this to the ECS service's load_balancer block."
  value       = aws_lb_target_group.this.arn
}

output "target_group_name" {
  description = "Target group name."
  value       = aws_lb_target_group.this.name
}

output "listener_arn" {
  description = "Listener ARN."
  value       = aws_lb_listener.this.arn
}
