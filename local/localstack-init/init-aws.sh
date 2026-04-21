#!/bin/bash
# LocalStack init hook — creates the S3 bucket, SQS queue, and DLQ the app expects.
set -euo pipefail

BUCKET="${PGSCP_S3_RAW_BUCKET:-pgscp-raw-events-local}"
QUEUE="${PGSCP_SQS_QUEUE_NAME:-pgscp-events-local}"
DLQ="${QUEUE}-dlq"
INVESTIGATIONS_QUEUE="${PGSCP_INVESTIGATIONS_QUEUE_NAME:-pgscp-investigations-local}"
INVESTIGATIONS_DLQ="${INVESTIGATIONS_QUEUE}-dlq"
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

INV_DLQ_URL=$(awslocal sqs create-queue --queue-name "${INVESTIGATIONS_DLQ}" --query QueueUrl --output text)
INV_DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url "${INV_DLQ_URL}" --attribute-names QueueArn --query Attributes.QueueArn --output text)

awslocal sqs create-queue \
  --queue-name "${INVESTIGATIONS_QUEUE}" \
  --attributes "{\"VisibilityTimeout\":\"180\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${INV_DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"}" \
  || true

echo "localstack init: bucket=${BUCKET} events_queue=${QUEUE} investigations_queue=${INVESTIGATIONS_QUEUE} ready"
