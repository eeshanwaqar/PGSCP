#!/bin/bash
# LocalStack init hook — creates the S3 bucket, SQS queue, and DLQ the app expects.
set -euo pipefail

BUCKET="${PGSCP_S3_RAW_BUCKET:-pgscp-raw-events-local}"
QUEUE="${PGSCP_SQS_QUEUE_NAME:-pgscp-events-local}"
DLQ="${QUEUE}-dlq"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION="${REGION}"

awslocal s3 mb "s3://${BUCKET}" || true

DLQ_URL=$(awslocal sqs create-queue --queue-name "${DLQ}" --query QueueUrl --output text)
DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url "${DLQ_URL}" --attribute-names QueueArn --query Attributes.QueueArn --output text)

awslocal sqs create-queue \
  --queue-name "${QUEUE}" \
  --attributes "{\"VisibilityTimeout\":\"60\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}" \
  || true

echo "localstack init: bucket=${BUCKET} queue=${QUEUE} dlq=${DLQ} ready"
