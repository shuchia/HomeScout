resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "homescout-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "homescout-${var.environment}-db-subnet"
    Environment = var.environment
  }
}

resource "aws_db_instance" "main" {
  identifier     = "homescout-${var.environment}"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password.result

  multi_az            = var.multi_az
  publicly_accessible = false

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.security_group_id]

  backup_retention_period = var.backup_retention_period
  deletion_protection     = var.deletion_protection

  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "homescout-prod-final" : null

  tags = {
    Name        = "homescout-${var.environment}"
    Environment = var.environment
  }
}

# Store password in Secrets Manager
resource "aws_secretsmanager_secret" "db_password" {
  name = "homescout/${var.environment}/db-password"
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id = aws_secretsmanager_secret.db_password.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db_password.result
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = var.db_name
  })
}
