resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "snugd-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "snugd-${var.environment}-db-subnet"
    Environment = var.environment
  }
}

resource "aws_db_instance" "main" {
  identifier     = "snugd-${var.environment}"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

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
  final_snapshot_identifier = var.environment == "prod" ? "snugd-prod-final" : null

  # Read only on create. On restore, RDS takes db_name and username from the
  # snapshot (both default to "snugd", same as QA) and the provider applies
  # `password` in a follow-up modify, so snugd/{env}/db-password stays right.
  snapshot_identifier = var.snapshot_identifier

  lifecycle {
    # snapshot_identifier forces replacement when it changes. Without this,
    # clearing it after the bootstrap restore would destroy and recreate the
    # database.
    # engine_version: RDS applies minor upgrades itself (QA went 16.6 ->
    # 16.13), after which a pinned minor reads as a downgrade on every plan.
    # The variable sets the version at create; major upgrades are deliberate
    # and done outside Terraform, then the variable is updated to match.
    ignore_changes = [snapshot_identifier, engine_version]
  }

  tags = {
    Name        = "snugd-${var.environment}"
    Environment = var.environment
  }
}

# Store password in Secrets Manager
resource "aws_secretsmanager_secret" "db_password" {
  name = "snugd/${var.environment}/db-password"
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
