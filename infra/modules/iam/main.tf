#
# Task roles.
#
# `execution` role is shared by every ECS task (ECR pull, CW log writes, Secrets
# injection into the container env). `task_*` roles are what the application
# code inside the container assumes at runtime — each is narrowed to the exact
# resources that service needs.
#

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  ecs_task_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# --------------------------------------------------------------------------- #
#  Task execution role — shared by api/worker/investigator
# --------------------------------------------------------------------------- #

resource "aws_iam_role" "task_execution" {
  name               = "${var.name_prefix}-task-execution"
  assume_role_policy = local.ecs_task_trust
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "task_execution_secrets" {
  count = length(var.secret_arns) == 0 ? 0 : 1

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [var.app_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  count  = length(var.secret_arns) == 0 ? 0 : 1
  name   = "secrets-injection"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets[0].json
}

# --------------------------------------------------------------------------- #
#  API task role
#   - s3:PutObject on the raw bucket (only under raw/ prefix)
#   - sqs:SendMessage to the events queue
#   - kms:GenerateDataKey for the app KMS key
#   - cloudwatch logs create-log-stream+put-log-events on own log group
# --------------------------------------------------------------------------- #

resource "aws_iam_role" "api_task" {
  name               = "${var.name_prefix}-api-task"
  assume_role_policy = local.ecs_task_trust
}

data "aws_iam_policy_document" "api_task" {
  statement {
    sid    = "WriteRawEvents"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl",
    ]
    resources = ["${var.raw_bucket_arn}/raw/*"]
  }

  statement {
    sid       = "ListOwnRawPrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.raw_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*"]
    }
  }

  dynamic "statement" {
    for_each = var.events_queue_arn == "" ? [] : [1]
    content {
      sid       = "EnqueueEvents"
      effect    = "Allow"
      actions   = ["sqs:SendMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
      resources = [var.events_queue_arn]
    }
  }

  statement {
    sid    = "KmsEncryptRaw"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:GenerateDataKey*",
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [var.app_kms_key_arn]
  }

  dynamic "statement" {
    for_each = var.api_log_group_arn == "" ? [] : [1]
    content {
      sid       = "WriteOwnLogs"
      effect    = "Allow"
      actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      resources = ["${var.api_log_group_arn}:*"]
    }
  }
}

resource "aws_iam_role_policy" "api_task" {
  name   = "api-task-policy"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.api_task.json
}

# --------------------------------------------------------------------------- #
#  Worker task role
#   - sqs:ReceiveMessage + DeleteMessage on events queue (+ ChangeVisibility)
#   - sqs:SendMessage on investigations queue (to hand off to investigator)
#   - s3:GetObject on raw bucket
#   - kms:Decrypt on app key
#   - secretsmanager:GetSecretValue on partner credentials
# --------------------------------------------------------------------------- #

resource "aws_iam_role" "worker_task" {
  name               = "${var.name_prefix}-worker-task"
  assume_role_policy = local.ecs_task_trust
}

data "aws_iam_policy_document" "worker_task" {
  dynamic "statement" {
    for_each = var.events_queue_arn == "" ? [] : [1]
    content {
      sid    = "ConsumeEvents"
      effect = "Allow"
      actions = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
      ]
      resources = [var.events_queue_arn]
    }
  }

  dynamic "statement" {
    for_each = var.investigations_queue_arn == "" ? [] : [1]
    content {
      sid       = "EnqueueInvestigations"
      effect    = "Allow"
      actions   = ["sqs:SendMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
      resources = [var.investigations_queue_arn]
    }
  }

  statement {
    sid       = "ReadRawEvents"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.raw_bucket_arn}/raw/*"]
  }

  statement {
    sid       = "ListRawBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.raw_bucket_arn]
  }

  statement {
    sid       = "KmsDecryptRaw"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [var.app_kms_key_arn]
  }

  dynamic "statement" {
    for_each = length(var.secret_arns) == 0 ? [] : [1]
    content {
      sid       = "ReadPartnerSecrets"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = var.secret_arns
    }
  }

  dynamic "statement" {
    for_each = var.worker_log_group_arn == "" ? [] : [1]
    content {
      sid       = "WriteOwnLogs"
      effect    = "Allow"
      actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      resources = ["${var.worker_log_group_arn}:*"]
    }
  }
}

resource "aws_iam_role_policy" "worker_task" {
  name   = "worker-task-policy"
  role   = aws_iam_role.worker_task.id
  policy = data.aws_iam_policy_document.worker_task.json
}

# --------------------------------------------------------------------------- #
#  Investigator task role
#   - sqs:ReceiveMessage on investigations queue
#   - s3:GetObject on raw events
#   - bedrock:InvokeModel on the configured Claude model ARNs
#   - logs:StartQuery/GetQueryResults on api + worker log groups (not all logs)
#   - secretsmanager:GetSecretValue on bedrock config + db creds
# --------------------------------------------------------------------------- #

resource "aws_iam_role" "investigator_task" {
  name               = "${var.name_prefix}-investigator-task"
  assume_role_policy = local.ecs_task_trust
}

data "aws_iam_policy_document" "investigator_task" {
  dynamic "statement" {
    for_each = var.investigations_queue_arn == "" ? [] : [1]
    content {
      sid    = "ConsumeInvestigations"
      effect = "Allow"
      actions = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes",
        "sqs:GetQueueUrl",
      ]
      resources = [var.investigations_queue_arn]
    }
  }

  statement {
    sid       = "ReadRawEvents"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.raw_bucket_arn}/raw/*"]
  }

  statement {
    sid       = "KmsDecryptRaw"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [var.app_kms_key_arn]
  }

  statement {
    sid       = "BedrockInvoke"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = var.bedrock_model_arns
  }

  dynamic "statement" {
    for_each = var.api_log_group_arn == "" && var.worker_log_group_arn == "" ? [] : [1]
    content {
      sid    = "QueryPeerLogs"
      effect = "Allow"
      actions = [
        "logs:StartQuery",
        "logs:GetQueryResults",
        "logs:StopQuery",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
      ]
      resources = compact([
        var.api_log_group_arn == "" ? "" : "${var.api_log_group_arn}:*",
        var.worker_log_group_arn == "" ? "" : "${var.worker_log_group_arn}:*",
      ])
    }
  }

  dynamic "statement" {
    for_each = var.investigator_log_group_arn == "" ? [] : [1]
    content {
      sid       = "WriteOwnLogs"
      effect    = "Allow"
      actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      resources = ["${var.investigator_log_group_arn}:*"]
    }
  }

  dynamic "statement" {
    for_each = length(var.secret_arns) == 0 ? [] : [1]
    content {
      sid       = "ReadConfigSecrets"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = var.secret_arns
    }
  }
}

resource "aws_iam_role_policy" "investigator_task" {
  name   = "investigator-task-policy"
  role   = aws_iam_role.investigator_task.id
  policy = data.aws_iam_policy_document.investigator_task.json
}
