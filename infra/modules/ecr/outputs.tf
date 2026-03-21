output "repository_url" {
  value       = aws_ecr_repository.backend.repository_url
  description = "ECR repository URL"
}

output "repository_arn" {
  value       = aws_ecr_repository.backend.arn
  description = "ECR repository ARN"
}
