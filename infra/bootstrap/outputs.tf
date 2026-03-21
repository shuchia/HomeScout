output "state_bucket_name" {
  value       = aws_s3_bucket.terraform_state.id
  description = "S3 bucket for Terraform state"
}

output "lock_table_name" {
  value       = aws_dynamodb_table.terraform_locks.id
  description = "DynamoDB table for Terraform state locking"
}
