output "endpoint" {
  value = aws_db_instance.main.address
}

output "port" {
  value = aws_db_instance.main.port
}

output "database_url" {
  value     = "postgresql+asyncpg://${var.db_username}:${random_password.db_password.result}@${aws_db_instance.main.address}:${aws_db_instance.main.port}/${var.db_name}"
  sensitive = true
}

output "db_password_secret_arn" {
  value = aws_secretsmanager_secret.db_password.arn
}
