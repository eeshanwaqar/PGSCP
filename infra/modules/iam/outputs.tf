output "task_execution_role_arn" {
  value = aws_iam_role.task_execution.arn
}

output "task_execution_role_name" {
  value = aws_iam_role.task_execution.name
}

output "api_task_role_arn" {
  value = aws_iam_role.api_task.arn
}

output "worker_task_role_arn" {
  value = aws_iam_role.worker_task.arn
}

output "investigator_task_role_arn" {
  value = aws_iam_role.investigator_task.arn
}
