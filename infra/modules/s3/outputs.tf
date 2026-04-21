output "raw_bucket_name" {
  value = aws_s3_bucket.raw.bucket
}

output "raw_bucket_arn" {
  value = aws_s3_bucket.raw.arn
}

output "logs_bucket_name" {
  value = aws_s3_bucket.logs.bucket
}

output "logs_bucket_arn" {
  value = aws_s3_bucket.logs.arn
}

output "app_kms_key_arn" {
  value = aws_kms_key.app.arn
}

output "app_kms_alias" {
  value = aws_kms_alias.app.name
}
