#
# Generic main-queue + DLQ pair. Instantiate once per logical queue.
#
# The queue is KMS-encrypted with the app CMK so any worker that can consume
# must also have kms:Decrypt on the same key — handled by the iam module.
#

locals {
  full_name = "${var.name_prefix}-${var.queue_name}"
  dlq_name  = "${local.full_name}-dlq"
}

resource "aws_sqs_queue" "dlq" {
  name                      = local.dlq_name
  message_retention_seconds = var.dlq_message_retention_seconds

  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = 300

  tags = {
    Name = local.dlq_name
    Role = "dead-letter"
  }
}

resource "aws_sqs_queue" "main" {
  name                       = local.full_name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = var.receive_wait_time_seconds

  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = 300

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.dlq_max_receive_count
  })

  tags = {
    Name = local.full_name
    Role = "main"
  }
}

# Tell the DLQ which source queues may redrive back to it. Without this the
# operator cannot use the AWS console "Start DLQ redrive" action.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.main.arn]
  })
}
