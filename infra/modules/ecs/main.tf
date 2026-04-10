resource "aws_ecs_cluster" "main" {
  name = "snugd-${var.environment}"

  setting {
    name  = "containerInsights"
    value = var.environment == "prod" ? "enabled" : "disabled"
  }

  tags = {
    Environment = var.environment
  }
}

# --- CloudWatch Log Groups ---
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/snugd-${var.environment}/api"
  retention_in_days = var.environment == "prod" ? 30 : (var.environment == "qa" ? 14 : 7)
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/snugd-${var.environment}/worker"
  retention_in_days = var.environment == "prod" ? 30 : (var.environment == "qa" ? 14 : 7)
}

resource "aws_cloudwatch_log_group" "beat" {
  name              = "/ecs/snugd-${var.environment}/beat"
  retention_in_days = var.environment == "prod" ? 30 : (var.environment == "qa" ? 14 : 7)
}

# --- Shared secret references ---
locals {
  secret_keys = [
    "ANTHROPIC_API_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_ID",
    "APIFY_API_TOKEN",
    "RESEND_API_KEY",
    "SCRAPINGBEE_API_KEY",
  ]

  secrets = [
    for key in local.secret_keys : {
      name      = key
      valueFrom = "${var.secrets_arn}:${key}::"
    }
  ]

  common_environment = [
    { name = "USE_DATABASE", value = "true" },
    { name = "FRONTEND_URL", value = var.frontend_url },
    { name = "LOG_LEVEL", value = var.log_level },
    { name = "PYTHONUNBUFFERED", value = "1" },
  ]
}

# --- API Task Definition ---
resource "aws_ecs_task_definition" "api" {
  family                   = "snugd-${var.environment}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "api"
    image = "${var.ecr_repository_url}:${var.image_tag}"

    environment = concat(local.common_environment, [
      { name = "SERVICE_TYPE", value = "api" },
    ])

    secrets = local.secrets

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

# --- Worker Task Definition ---
resource "aws_ecs_task_definition" "worker" {
  family                   = "snugd-${var.environment}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "worker"
    image = "${var.ecr_repository_url}:${var.image_tag}"

    environment = concat(local.common_environment, [
      { name = "SERVICE_TYPE", value = "worker" },
    ])

    secrets = local.secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}

# --- Beat Task Definition ---
resource "aws_ecs_task_definition" "beat" {
  family                   = "snugd-${var.environment}-beat"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "beat"
    image = "${var.ecr_repository_url}:${var.image_tag}"

    environment = concat(local.common_environment, [
      { name = "SERVICE_TYPE", value = "beat" },
    ])

    secrets = local.secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.beat.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "beat"
      }
    }
  }])
}

# --- ECS Services ---
resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "api"
    container_port   = 8000
  }
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }
}

resource "aws_ecs_service" "beat" {
  name            = "beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.beat.arn
  desired_count   = var.beat_desired_count
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }
}
