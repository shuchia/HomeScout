# Production Deployment & CI/CD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Set up a complete CI/CD pipeline and multi-environment (dev/qa/prod) deployment for HomeScout on AWS ECS Fargate + Vercel.

**Architecture:** Backend Docker image deployed to ECS Fargate (3 services: API, Celery Worker, Celery Beat) per environment. Frontend on Vercel. Terraform modules for VPC, ECS, RDS, ElastiCache, ALB, ECR. GitHub Actions for CI and deployment. AWS Secrets Manager for configuration.

**Tech Stack:** Docker, Terraform (AWS provider), GitHub Actions, AWS (ECS Fargate, RDS PostgreSQL, ElastiCache Redis, ALB, ECR, CloudWatch, Secrets Manager, Route53, ACM), Vercel.

**Design doc:** `docs/plans/2026-03-21-production-deployment-design.md`

---

### Task 1: Backend Dockerfile

Create a multi-stage Dockerfile for the FastAPI backend. One image serves three roles (api, worker, beat) based on `SERVICE_TYPE` env var.

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `backend/docker-entrypoint.sh`

**Step 1: Create `.dockerignore`**

Create `backend/.dockerignore`:

```
.venv/
__pycache__/
*.pyc
.env
.env.*
*.egg-info/
.git/
.github/
tests/
scripts/
*.md
.mypy_cache/
.pytest_cache/
.ruff_cache/
```

**Step 2: Create the entrypoint script**

Create `backend/docker-entrypoint.sh`:

```bash
#!/bin/bash
set -e

SERVICE_TYPE=${SERVICE_TYPE:-api}

case "$SERVICE_TYPE" in
  api)
    echo "Starting FastAPI API server..."
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    echo "Starting Celery worker..."
    exec celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance
    ;;
  beat)
    echo "Starting Celery beat scheduler..."
    exec celery -A app.celery_app beat --loglevel=info
    ;;
  migrate)
    echo "Running Alembic migrations..."
    exec alembic upgrade head
    ;;
  *)
    echo "Unknown SERVICE_TYPE: $SERVICE_TYPE"
    echo "Valid values: api, worker, beat, migrate"
    exit 1
    ;;
esac
```

**Step 3: Create the Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
# ---- Stage 1: Build dependencies ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: Runtime image ----
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY . .

# Copy and set entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Default environment
ENV SERVICE_TYPE=api
ENV PYTHONUNBUFFERED=1

# Health check for API service (ignored by worker/beat)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD if [ "$SERVICE_TYPE" = "api" ]; then curl -f http://localhost:8000/health || exit 1; else exit 0; fi

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
```

**Step 4: Build and verify the Docker image locally**

Run:
```bash
cd backend
docker build -t homescout-backend:local .
```
Expected: Build completes successfully.

Run:
```bash
docker run --rm -e SERVICE_TYPE=api -e USE_DATABASE=false -p 8000:8000 homescout-backend:local &
sleep 5
curl http://localhost:8000/health
docker stop $(docker ps -q --filter ancestor=homescout-backend:local)
```
Expected: `{"status":"healthy",...}`

**Step 5: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore backend/docker-entrypoint.sh
git commit -m "feat: add backend Dockerfile with multi-service entrypoint"
```

---

### Task 2: Terraform State Backend (S3 + DynamoDB)

Set up Terraform remote state storage. This is a one-time bootstrap — you run it once to create the S3 bucket and DynamoDB table that all future Terraform runs use.

**Files:**
- Create: `infra/bootstrap/main.tf`
- Create: `infra/bootstrap/variables.tf`
- Create: `infra/bootstrap/outputs.tf`

**Step 1: Create bootstrap Terraform config**

Create `infra/bootstrap/main.tf`:

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = "homescout-terraform-state"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "terraform_locks" {
  name         = "homescout-terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
```

Create `infra/bootstrap/variables.tf`:

```hcl
variable "aws_region" {
  description = "AWS region for Terraform state resources"
  type        = string
  default     = "us-east-1"
}
```

Create `infra/bootstrap/outputs.tf`:

```hcl
output "state_bucket_name" {
  value       = aws_s3_bucket.terraform_state.id
  description = "S3 bucket for Terraform state"
}

output "lock_table_name" {
  value       = aws_dynamodb_table.terraform_locks.id
  description = "DynamoDB table for Terraform state locking"
}
```

**Step 2: Run bootstrap (one-time)**

```bash
cd infra/bootstrap
terraform init
terraform plan
terraform apply
```
Expected: S3 bucket `homescout-terraform-state` and DynamoDB table `homescout-terraform-locks` created.

**Step 3: Commit**

```bash
git add infra/bootstrap/
git commit -m "feat: add Terraform bootstrap for state backend (S3 + DynamoDB)"
```

---

### Task 3: Terraform ECR Module

Create the shared ECR repository for Docker images.

**Files:**
- Create: `infra/modules/ecr/main.tf`
- Create: `infra/modules/ecr/variables.tf`
- Create: `infra/modules/ecr/outputs.tf`

**Step 1: Create ECR module**

Create `infra/modules/ecr/main.tf`:

```hcl
resource "aws_ecr_repository" "backend" {
  name                 = var.repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 20 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
```

Create `infra/modules/ecr/variables.tf`:

```hcl
variable "repository_name" {
  description = "Name of the ECR repository"
  type        = string
  default     = "homescout-backend"
}
```

Create `infra/modules/ecr/outputs.tf`:

```hcl
output "repository_url" {
  value       = aws_ecr_repository.backend.repository_url
  description = "ECR repository URL"
}

output "repository_arn" {
  value       = aws_ecr_repository.backend.arn
  description = "ECR repository ARN"
}
```

**Step 2: Commit**

```bash
git add infra/modules/ecr/
git commit -m "feat: add Terraform ECR module for Docker image registry"
```

---

### Task 4: Terraform Networking Module

VPC with public and private subnets, NAT gateway, and security groups.

**Files:**
- Create: `infra/modules/networking/main.tf`
- Create: `infra/modules/networking/variables.tf`
- Create: `infra/modules/networking/outputs.tf`

**Step 1: Create networking module**

Create `infra/modules/networking/variables.tf`:

```hcl
variable "environment" {
  description = "Environment name (dev, qa, prod)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "enable_redundant_nat" {
  description = "Create NAT Gateway per AZ (true for prod)"
  type        = bool
  default     = false
}
```

Create `infra/modules/networking/main.tf`:

```hcl
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

# --- VPC ---
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "homescout-${var.environment}"
    Environment = var.environment
  }
}

# --- Internet Gateway ---
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "homescout-${var.environment}-igw"
    Environment = var.environment
  }
}

# --- Public Subnets ---
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name        = "homescout-${var.environment}-public-${local.azs[count.index]}"
    Environment = var.environment
  }
}

# --- Private Subnets ---
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]

  tags = {
    Name        = "homescout-${var.environment}-private-${local.azs[count.index]}"
    Environment = var.environment
  }
}

# --- NAT Gateway ---
resource "aws_eip" "nat" {
  count  = var.enable_redundant_nat ? 2 : 1
  domain = "vpc"

  tags = {
    Name        = "homescout-${var.environment}-nat-eip-${count.index}"
    Environment = var.environment
  }
}

resource "aws_nat_gateway" "main" {
  count         = var.enable_redundant_nat ? 2 : 1
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name        = "homescout-${var.environment}-nat-${count.index}"
    Environment = var.environment
  }

  depends_on = [aws_internet_gateway.main]
}

# --- Route Tables ---
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name        = "homescout-${var.environment}-public-rt"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  count  = 2
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[var.enable_redundant_nat ? count.index : 0].id
  }

  tags = {
    Name        = "homescout-${var.environment}-private-rt-${count.index}"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# --- Security Groups ---
resource "aws_security_group" "alb" {
  name_prefix = "homescout-${var.environment}-alb-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "homescout-${var.environment}-alb-sg"
    Environment = var.environment
  }
}

resource "aws_security_group" "ecs" {
  name_prefix = "homescout-${var.environment}-ecs-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "homescout-${var.environment}-ecs-sg"
    Environment = var.environment
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "homescout-${var.environment}-rds-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = {
    Name        = "homescout-${var.environment}-rds-sg"
    Environment = var.environment
  }
}

resource "aws_security_group" "redis" {
  name_prefix = "homescout-${var.environment}-redis-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = {
    Name        = "homescout-${var.environment}-redis-sg"
    Environment = var.environment
  }
}
```

Create `infra/modules/networking/outputs.tf`:

```hcl
output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}
```

**Step 2: Commit**

```bash
git add infra/modules/networking/
git commit -m "feat: add Terraform networking module (VPC, subnets, NAT, security groups)"
```

---

### Task 5: Terraform RDS Module

Managed PostgreSQL instance per environment.

**Files:**
- Create: `infra/modules/rds/main.tf`
- Create: `infra/modules/rds/variables.tf`
- Create: `infra/modules/rds/outputs.tf`

**Step 1: Create RDS module**

Create `infra/modules/rds/variables.tf`:

```hcl
variable "environment" {
  type = string
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "backup_retention_period" {
  type    = number
  default = 1
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "db_name" {
  type    = string
  default = "homescout"
}

variable "db_username" {
  type    = string
  default = "homescout"
}
```

Create `infra/modules/rds/main.tf`:

```hcl
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
```

Create `infra/modules/rds/outputs.tf`:

```hcl
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
```

**Step 2: Commit**

```bash
git add infra/modules/rds/
git commit -m "feat: add Terraform RDS module for managed PostgreSQL"
```

---

### Task 6: Terraform ElastiCache Module

Managed Redis per environment.

**Files:**
- Create: `infra/modules/elasticache/main.tf`
- Create: `infra/modules/elasticache/variables.tf`
- Create: `infra/modules/elasticache/outputs.tf`

**Step 1: Create ElastiCache module**

Create `infra/modules/elasticache/variables.tf`:

```hcl
variable "environment" {
  type = string
}

variable "node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "num_cache_nodes" {
  type    = number
  default = 1
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}
```

Create `infra/modules/elasticache/main.tf`:

```hcl
resource "aws_elasticache_subnet_group" "main" {
  name       = "homescout-${var.environment}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "homescout-${var.environment}"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.node_type
  num_cache_nodes      = var.num_cache_nodes
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [var.security_group_id]

  tags = {
    Name        = "homescout-${var.environment}"
    Environment = var.environment
  }
}
```

Create `infra/modules/elasticache/outputs.tf`:

```hcl
output "endpoint" {
  value = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "port" {
  value = aws_elasticache_cluster.main.cache_nodes[0].port
}

output "redis_url" {
  value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:${aws_elasticache_cluster.main.cache_nodes[0].port}/0"
}
```

**Step 2: Commit**

```bash
git add infra/modules/elasticache/
git commit -m "feat: add Terraform ElastiCache module for managed Redis"
```

---

### Task 7: Terraform ALB Module

Application Load Balancer with HTTPS termination.

**Files:**
- Create: `infra/modules/alb/main.tf`
- Create: `infra/modules/alb/variables.tf`
- Create: `infra/modules/alb/outputs.tf`

**Step 1: Create ALB module**

Create `infra/modules/alb/variables.tf`:

```hcl
variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
}

variable "health_check_path" {
  type    = string
  default = "/health"
}
```

Create `infra/modules/alb/main.tf`:

```hcl
resource "aws_lb" "main" {
  name               = "homescout-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets            = var.public_subnet_ids

  tags = {
    Name        = "homescout-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "api" {
  name        = "homescout-${var.environment}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = var.health_check_path
    matcher             = "200"
  }

  tags = {
    Name        = "homescout-${var.environment}-api"
    Environment = var.environment
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
```

Create `infra/modules/alb/outputs.tf`:

```hcl
output "dns_name" {
  value = aws_lb.main.dns_name
}

output "zone_id" {
  value = aws_lb.main.zone_id
}

output "target_group_arn" {
  value = aws_lb_target_group.api.arn
}

output "listener_arn" {
  value = aws_lb_listener.https.arn
}
```

**Step 2: Commit**

```bash
git add infra/modules/alb/
git commit -m "feat: add Terraform ALB module with HTTPS and health checks"
```

---

### Task 8: Terraform ECS Module

ECS cluster, task definitions, and services for API, Worker, and Beat.

**Files:**
- Create: `infra/modules/ecs/main.tf`
- Create: `infra/modules/ecs/variables.tf`
- Create: `infra/modules/ecs/outputs.tf`
- Create: `infra/modules/ecs/iam.tf`

**Step 1: Create ECS IAM roles**

Create `infra/modules/ecs/iam.tf`:

```hcl
# Task execution role (used by ECS to pull images, write logs, read secrets)
resource "aws_iam_role" "ecs_execution" {
  name = "homescout-${var.environment}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "secrets-access"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = [var.secrets_arn]
    }]
  })
}

# Task role (used by the application itself)
resource "aws_iam_role" "ecs_task" {
  name = "homescout-${var.environment}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

# Allow task role to access S3 for image caching
resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "s3-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject"
      ]
      Resource = "arn:aws:s3:::homescout-images/*"
    }]
  })
}
```

**Step 2: Create ECS variables**

Create `infra/modules/ecs/variables.tf`:

```hcl
variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "ecr_repository_url" {
  type = string
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "ecs_security_group_id" {
  type = string
}

variable "target_group_arn" {
  type = string
}

variable "secrets_arn" {
  description = "ARN of the Secrets Manager secret for app config"
  type        = string
}

# Service sizing
variable "api_cpu" {
  type    = number
  default = 256
}

variable "api_memory" {
  type    = number
  default = 512
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "worker_cpu" {
  type    = number
  default = 256
}

variable "worker_memory" {
  type    = number
  default = 512
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "frontend_url" {
  type = string
}

variable "log_level" {
  type    = string
  default = "INFO"
}
```

**Step 3: Create ECS main config**

Create `infra/modules/ecs/main.tf`:

```hcl
resource "aws_ecs_cluster" "main" {
  name = "homescout-${var.environment}"

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
  name              = "/ecs/homescout-${var.environment}/api"
  retention_in_days = var.environment == "prod" ? 30 : (var.environment == "qa" ? 14 : 7)
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/homescout-${var.environment}/worker"
  retention_in_days = var.environment == "prod" ? 30 : (var.environment == "qa" ? 14 : 7)
}

resource "aws_cloudwatch_log_group" "beat" {
  name              = "/ecs/homescout-${var.environment}/beat"
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
  family                   = "homescout-${var.environment}-api"
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
  family                   = "homescout-${var.environment}-worker"
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
  family                   = "homescout-${var.environment}-beat"
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
  desired_count   = 1
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
```

Create `infra/modules/ecs/outputs.tf`:

```hcl
output "cluster_id" {
  value = aws_ecs_cluster.main.id
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "api_service_name" {
  value = aws_ecs_service.api.name
}

output "api_task_definition_family" {
  value = aws_ecs_task_definition.api.family
}

output "migration_task_definition_arn" {
  value       = aws_ecs_task_definition.api.arn
  description = "Use with command override SERVICE_TYPE=migrate for Alembic migrations"
}
```

**Step 4: Commit**

```bash
git add infra/modules/ecs/
git commit -m "feat: add Terraform ECS module (cluster, services, task definitions, IAM)"
```

---

### Task 9: Terraform Root Configuration & Environment Tfvars

Wire all modules together and create per-environment variable files.

**Files:**
- Create: `infra/main.tf`
- Create: `infra/variables.tf`
- Create: `infra/outputs.tf`
- Create: `infra/environments/dev.tfvars`
- Create: `infra/environments/qa.tfvars`
- Create: `infra/environments/prod.tfvars`
- Create: `infra/.gitignore`

**Step 1: Create infra `.gitignore`**

Create `infra/.gitignore`:

```
.terraform/
*.tfstate
*.tfstate.*
*.tfplan
.terraform.lock.hcl
```

**Step 2: Create root variables**

Create `infra/variables.tf`:

```hcl
variable "environment" {
  description = "Environment name (dev, qa, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "enable_redundant_nat" {
  type    = bool
  default = false
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# RDS
variable "rds_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "rds_allocated_storage" {
  type    = number
  default = 20
}

variable "rds_multi_az" {
  type    = bool
  default = false
}

variable "rds_backup_retention" {
  type    = number
  default = 1
}

variable "rds_deletion_protection" {
  type    = bool
  default = false
}

# ElastiCache
variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "redis_num_nodes" {
  type    = number
  default = 1
}

# ECS
variable "api_cpu" {
  type    = number
  default = 256
}

variable "api_memory" {
  type    = number
  default = 512
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "worker_cpu" {
  type    = number
  default = 256
}

variable "worker_memory" {
  type    = number
  default = 512
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "frontend_url" {
  type = string
}

variable "log_level" {
  type    = string
  default = "INFO"
}
```

**Step 3: Create root main.tf**

Create `infra/main.tf`:

```hcl
terraform {
  required_version = ">= 1.5"

  backend "s3" {
    bucket         = "homescout-terraform-state"
    key            = "infra/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "homescout-terraform-locks"
    encrypt        = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "homescout"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# --- Secrets Manager (application secrets — populated manually) ---
resource "aws_secretsmanager_secret" "app_secrets" {
  name = "homescout/${var.environment}/secrets"
}

# --- Modules ---
module "ecr" {
  source          = "./modules/ecr"
  repository_name = "homescout-backend"
}

module "networking" {
  source               = "./modules/networking"
  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  aws_region           = var.aws_region
  enable_redundant_nat = var.enable_redundant_nat
}

module "rds" {
  source                  = "./modules/rds"
  environment             = var.environment
  instance_class          = var.rds_instance_class
  allocated_storage       = var.rds_allocated_storage
  multi_az                = var.rds_multi_az
  backup_retention_period = var.rds_backup_retention
  deletion_protection     = var.rds_deletion_protection
  private_subnet_ids      = module.networking.private_subnet_ids
  security_group_id       = module.networking.rds_security_group_id
}

module "elasticache" {
  source             = "./modules/elasticache"
  environment        = var.environment
  node_type          = var.redis_node_type
  num_cache_nodes    = var.redis_num_nodes
  private_subnet_ids = module.networking.private_subnet_ids
  security_group_id  = module.networking.redis_security_group_id
}

module "alb" {
  source            = "./modules/alb"
  environment       = var.environment
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
  security_group_id = module.networking.alb_security_group_id
  certificate_arn   = var.certificate_arn
}

module "ecs" {
  source                = "./modules/ecs"
  environment           = var.environment
  aws_region            = var.aws_region
  ecr_repository_url    = module.ecr.repository_url
  image_tag             = var.image_tag
  private_subnet_ids    = module.networking.private_subnet_ids
  ecs_security_group_id = module.networking.ecs_security_group_id
  target_group_arn      = module.alb.target_group_arn
  secrets_arn           = aws_secretsmanager_secret.app_secrets.arn
  api_cpu               = var.api_cpu
  api_memory            = var.api_memory
  api_desired_count     = var.api_desired_count
  worker_cpu            = var.worker_cpu
  worker_memory         = var.worker_memory
  worker_desired_count  = var.worker_desired_count
  frontend_url          = var.frontend_url
  log_level             = var.log_level
}
```

**Step 4: Create outputs**

Create `infra/outputs.tf`:

```hcl
output "alb_dns_name" {
  value       = module.alb.dns_name
  description = "ALB DNS name — point your Route53 record here"
}

output "ecr_repository_url" {
  value       = module.ecr.repository_url
  description = "ECR repository URL for docker push"
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "redis_endpoint" {
  value = module.elasticache.endpoint
}
```

**Step 5: Create environment tfvars**

Create `infra/environments/dev.tfvars`:

```hcl
environment          = "dev"
vpc_cidr             = "10.0.0.0/16"
enable_redundant_nat = false
frontend_url         = "https://dev.homescout.app"
log_level            = "DEBUG"

# RDS
rds_instance_class    = "db.t4g.micro"
rds_allocated_storage = 20
rds_multi_az          = false
rds_backup_retention  = 1
rds_deletion_protection = false

# Redis
redis_node_type = "cache.t4g.micro"
redis_num_nodes = 1

# ECS
api_cpu            = 256
api_memory         = 512
api_desired_count  = 1
worker_cpu         = 256
worker_memory      = 512
worker_desired_count = 1
```

Create `infra/environments/qa.tfvars`:

```hcl
environment          = "qa"
vpc_cidr             = "10.1.0.0/16"
enable_redundant_nat = false
frontend_url         = "https://qa.homescout.app"
log_level            = "INFO"

# RDS
rds_instance_class    = "db.t4g.micro"
rds_allocated_storage = 20
rds_multi_az          = false
rds_backup_retention  = 1
rds_deletion_protection = false

# Redis
redis_node_type = "cache.t4g.micro"
redis_num_nodes = 1

# ECS
api_cpu            = 256
api_memory         = 512
api_desired_count  = 1
worker_cpu         = 256
worker_memory      = 512
worker_desired_count = 1
```

Create `infra/environments/prod.tfvars`:

```hcl
environment          = "prod"
vpc_cidr             = "10.2.0.0/16"
enable_redundant_nat = true
frontend_url         = "https://homescout.app"
log_level            = "WARNING"

# RDS
rds_instance_class    = "db.t4g.small"
rds_allocated_storage = 50
rds_multi_az          = true
rds_backup_retention  = 7
rds_deletion_protection = true

# Redis
redis_node_type = "cache.t4g.small"
redis_num_nodes = 1

# ECS
api_cpu            = 512
api_memory         = 1024
api_desired_count  = 2
worker_cpu         = 512
worker_memory      = 1024
worker_desired_count = 1
```

**Step 6: Validate Terraform**

```bash
cd infra
terraform init -backend=false
terraform validate
```
Expected: `Success! The configuration is valid.`

**Step 7: Commit**

```bash
git add infra/main.tf infra/variables.tf infra/outputs.tf infra/environments/ infra/.gitignore
git commit -m "feat: add Terraform root config and environment tfvars (dev/qa/prod)"
```

---

### Task 10: GitHub Actions CI Workflow

Lint, test, and build verification on every PR.

**Files:**
- Create: `.github/workflows/ci.yml`

**Step 1: Create CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.head_ref }}
  cancel-in-progress: true

jobs:
  backend-lint-test:
    name: Backend Lint & Test
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        env:
          ANTHROPIC_API_KEY: test-key
          SUPABASE_JWT_SECRET: test-secret
          TESTING: "1"
        run: python -m pytest tests/ -v --tb=short

  backend-docker-build:
    name: Backend Docker Build
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t homescout-backend:ci ./backend

  frontend-lint-build:
    name: Frontend Lint & Build
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Type check
        run: npx tsc --noEmit

      - name: Build
        run: npm run build
        env:
          NEXT_PUBLIC_API_URL: http://localhost:8000
          NEXT_PUBLIC_SUPABASE_URL: https://test.supabase.co
          NEXT_PUBLIC_SUPABASE_ANON_KEY: test-key
```

**Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: add GitHub Actions CI workflow (lint, test, build)"
```

---

### Task 11: GitHub Actions Backend Deploy Workflow

Build, push to ECR, run migrations, and deploy to ECS. Supports dev (auto), qa (manual), and prod (manual + approval).

**Files:**
- Create: `.github/workflows/deploy-backend.yml`

**Step 1: Create deploy workflow**

Create `.github/workflows/deploy-backend.yml`:

```yaml
name: Deploy Backend

on:
  push:
    branches: [main]
    paths:
      - "backend/**"
      - ".github/workflows/deploy-backend.yml"
  workflow_dispatch:
    inputs:
      environment:
        description: "Environment to deploy to"
        required: true
        type: choice
        options:
          - dev
          - qa
          - prod

concurrency:
  group: deploy-backend-${{ github.event.inputs.environment || 'dev' }}

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: homescout-backend

jobs:
  build-and-push:
    name: Build & Push Docker Image
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.meta.outputs.image_tag }}

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Set image tag
        id: meta
        run: |
          ENV=${{ github.event.inputs.environment || 'dev' }}
          SHA=$(echo ${{ github.sha }} | cut -c1-7)
          echo "image_tag=${ENV}-${SHA}" >> "$GITHUB_OUTPUT"

      - name: Build and push Docker image
        run: |
          IMAGE=${{ steps.ecr-login.outputs.registry }}/${{ env.ECR_REPOSITORY }}:${{ steps.meta.outputs.image_tag }}
          docker build -t $IMAGE ./backend
          docker push $IMAGE

  deploy-dev:
    name: Deploy to Dev
    needs: build-and-push
    if: github.event.inputs.environment == 'dev' || github.event.inputs.environment == '' || github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: dev

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Run Alembic migrations
        run: |
          aws ecs run-task \
            --cluster homescout-dev \
            --task-definition homescout-dev-api \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={subnets=${{ secrets.DEV_PRIVATE_SUBNETS }},securityGroups=[${{ secrets.DEV_ECS_SG }}],assignPublicIp=DISABLED}" \
            --overrides '{"containerOverrides":[{"name":"api","environment":[{"name":"SERVICE_TYPE","value":"migrate"}]}]}' \
            --query 'tasks[0].taskArn' \
            --output text | xargs -I {} aws ecs wait tasks-stopped --cluster homescout-dev --tasks {}

      - name: Deploy ECS services
        run: |
          for SERVICE in api worker beat; do
            aws ecs update-service \
              --cluster homescout-dev \
              --service $SERVICE \
              --force-new-deployment \
              --no-cli-pager
          done

      - name: Wait for API service stability
        run: |
          aws ecs wait services-stable \
            --cluster homescout-dev \
            --services api

      - name: Smoke test
        run: |
          sleep 10
          curl -sf https://api-dev.homescout.app/health || exit 1
          echo "Smoke test passed"

  deploy-qa:
    name: Deploy to QA
    needs: build-and-push
    if: github.event.inputs.environment == 'qa'
    runs-on: ubuntu-latest
    environment: qa

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Retag image for QA
        run: |
          REGISTRY=$(aws ecr describe-repositories --repository-names ${{ env.ECR_REPOSITORY }} --query 'repositories[0].repositoryUri' --output text)
          SHA=$(echo ${{ github.sha }} | cut -c1-7)
          # Pull the dev image and retag as qa
          docker pull ${REGISTRY}:dev-${SHA}
          docker tag ${REGISTRY}:dev-${SHA} ${REGISTRY}:qa-${SHA}
          docker push ${REGISTRY}:qa-${SHA}

      - name: Run Alembic migrations
        run: |
          aws ecs run-task \
            --cluster homescout-qa \
            --task-definition homescout-qa-api \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={subnets=${{ secrets.QA_PRIVATE_SUBNETS }},securityGroups=[${{ secrets.QA_ECS_SG }}],assignPublicIp=DISABLED}" \
            --overrides '{"containerOverrides":[{"name":"api","environment":[{"name":"SERVICE_TYPE","value":"migrate"}]}]}' \
            --query 'tasks[0].taskArn' \
            --output text | xargs -I {} aws ecs wait tasks-stopped --cluster homescout-qa --tasks {}

      - name: Deploy ECS services
        run: |
          for SERVICE in api worker beat; do
            aws ecs update-service \
              --cluster homescout-qa \
              --service $SERVICE \
              --force-new-deployment \
              --no-cli-pager
          done

      - name: Wait for stability
        run: aws ecs wait services-stable --cluster homescout-qa --services api

      - name: Smoke test
        run: |
          sleep 10
          curl -sf https://api-qa.homescout.app/health || exit 1

  deploy-prod:
    name: Deploy to Prod
    needs: build-and-push
    if: github.event.inputs.environment == 'prod'
    runs-on: ubuntu-latest
    environment:
      name: prod
      # GitHub Environment protection rules enforce manual approval

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Retag image for Prod
        run: |
          REGISTRY=$(aws ecr describe-repositories --repository-names ${{ env.ECR_REPOSITORY }} --query 'repositories[0].repositoryUri' --output text)
          SHA=$(echo ${{ github.sha }} | cut -c1-7)
          docker pull ${REGISTRY}:qa-${SHA}
          docker tag ${REGISTRY}:qa-${SHA} ${REGISTRY}:prod-${SHA}
          docker push ${REGISTRY}:prod-${SHA}

      - name: Run Alembic migrations
        run: |
          aws ecs run-task \
            --cluster homescout-prod \
            --task-definition homescout-prod-api \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={subnets=${{ secrets.PROD_PRIVATE_SUBNETS }},securityGroups=[${{ secrets.PROD_ECS_SG }}],assignPublicIp=DISABLED}" \
            --overrides '{"containerOverrides":[{"name":"api","environment":[{"name":"SERVICE_TYPE","value":"migrate"}]}]}' \
            --query 'tasks[0].taskArn' \
            --output text | xargs -I {} aws ecs wait tasks-stopped --cluster homescout-prod --tasks {}

      - name: Deploy ECS services
        run: |
          for SERVICE in api worker beat; do
            aws ecs update-service \
              --cluster homescout-prod \
              --service $SERVICE \
              --force-new-deployment \
              --no-cli-pager
          done

      - name: Wait for stability
        run: aws ecs wait services-stable --cluster homescout-prod --services api

      - name: Smoke test
        run: |
          sleep 10
          curl -sf https://api.homescout.app/health || exit 1
```

**Step 2: Commit**

```bash
git add .github/workflows/deploy-backend.yml
git commit -m "feat: add GitHub Actions backend deploy workflow (dev/qa/prod)"
```

---

### Task 12: CloudWatch Alarms (Terraform)

Add production monitoring alarms to the ECS module.

**Files:**
- Create: `infra/modules/monitoring/main.tf`
- Create: `infra/modules/monitoring/variables.tf`

**Step 1: Create monitoring module**

Create `infra/modules/monitoring/variables.tf`:

```hcl
variable "environment" {
  type = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "ecs_api_service_name" {
  type = string
}

variable "alb_arn_suffix" {
  description = "ALB ARN suffix for CloudWatch metrics"
  type        = string
}

variable "target_group_arn_suffix" {
  description = "Target group ARN suffix for CloudWatch metrics"
  type        = string
}

variable "rds_instance_id" {
  type = string
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}
```

Create `infra/modules/monitoring/main.tf`:

```hcl
# --- SNS Topic for Alerts ---
resource "aws_sns_topic" "alerts" {
  count = var.environment == "prod" ? 1 : 0
  name  = "homescout-${var.environment}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.environment == "prod" && var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- API 5xx Error Rate ---
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "homescout-${var.environment}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 5
  period              = 300
  statistic           = "Sum"
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    TargetGroup  = var.target_group_arn_suffix
    LoadBalancer = var.alb_arn_suffix
  }
}

# --- API Latency p95 ---
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "homescout-${var.environment}-api-latency-p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 3
  period              = 300
  extended_statistic  = "p95"
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    TargetGroup  = var.target_group_arn_suffix
    LoadBalancer = var.alb_arn_suffix
  }
}

# --- RDS CPU ---
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "homescout-${var.environment}-rds-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 80
  period              = 600
  statistic           = "Average"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }
}

# --- RDS Free Storage ---
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "homescout-${var.environment}-rds-low-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  threshold           = 5368709120 # 5GB in bytes
  period              = 300
  statistic           = "Average"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }
}
```

**Step 2: Commit**

```bash
git add infra/modules/monitoring/
git commit -m "feat: add Terraform monitoring module (CloudWatch alarms, SNS alerts)"
```

---

### Task 13: Backend Structured JSON Logging

Switch from Python's default logger to structured JSON for CloudWatch compatibility.

**Files:**
- Modify: `backend/requirements.txt` (add `python-json-logger`)
- Create: `backend/app/logging_config.py`
- Modify: `backend/app/main.py:29-31` (replace logging.basicConfig)

**Step 1: Add dependency**

Add to `backend/requirements.txt`:

```
# Structured logging
python-json-logger==2.0.7
```

**Step 2: Create logging config**

Create `backend/app/logging_config.py`:

```python
"""Structured JSON logging for production (CloudWatch)."""
import logging
import os
import sys

from pythonjsonlogger import jsonlogger


def setup_logging():
    """Configure logging. JSON in production, standard format locally."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    is_production = os.getenv("SERVICE_TYPE") is not None  # Set in Docker

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if is_production:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    else:
        formatter = logging.Formatter(
            "%(levelname)-5.5s [%(name)s] %(message)s"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
```

**Step 3: Update main.py**

In `backend/app/main.py`, replace lines 29-31:

```python
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

With:

```python
# Configure logging
from app.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)
```

**Step 4: Install and test locally**

```bash
cd backend
source .venv/bin/activate
pip install python-json-logger==2.0.7
```

Run the backend and verify logs appear normally (non-JSON format locally since `SERVICE_TYPE` is not set):

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl http://localhost:8000/health
pkill -f "uvicorn app.main"
```

Expected: Logs in standard format locally. When `SERVICE_TYPE=api` is set (Docker), output is JSON.

**Step 5: Run backend tests**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v --tb=short
```
Expected: All tests pass (the logging change should not affect tests).

**Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/logging_config.py backend/app/main.py
git commit -m "feat: add structured JSON logging for CloudWatch compatibility"
```

---

### Task 14: Deploy Helper Script

A convenience script for common deployment operations.

**Files:**
- Create: `scripts/deploy.sh`

**Step 1: Create deploy script**

Create `scripts/deploy.sh`:

```bash
#!/bin/bash
set -euo pipefail

# HomeScout deployment helper
# Usage: ./scripts/deploy.sh <command> [environment]

COMMAND=${1:-help}
ENV=${2:-dev}
AWS_REGION=${AWS_REGION:-us-east-1}
ECR_REPO="homescout-backend"

usage() {
  echo "Usage: ./scripts/deploy.sh <command> [environment]"
  echo ""
  echo "Commands:"
  echo "  build          Build Docker image locally"
  echo "  push <env>     Push image to ECR for environment"
  echo "  deploy <env>   Deploy to ECS environment"
  echo "  migrate <env>  Run Alembic migrations on environment"
  echo "  status <env>   Check ECS service status"
  echo "  logs <env>     Tail CloudWatch logs for API service"
  echo "  tf-plan <env>  Run terraform plan for environment"
  echo "  tf-apply <env> Run terraform apply for environment"
  echo ""
  echo "Environments: dev, qa, prod"
}

get_ecr_url() {
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  echo "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
}

case "$COMMAND" in
  build)
    echo "Building Docker image..."
    docker build -t ${ECR_REPO}:local ./backend
    echo "Build complete: ${ECR_REPO}:local"
    ;;

  push)
    ECR_URL=$(get_ecr_url)
    SHA=$(git rev-parse --short HEAD)
    TAG="${ENV}-${SHA}"
    echo "Pushing ${ECR_URL}:${TAG}..."
    aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URL%%/*}
    docker tag ${ECR_REPO}:local ${ECR_URL}:${TAG}
    docker push ${ECR_URL}:${TAG}
    echo "Pushed: ${ECR_URL}:${TAG}"
    ;;

  deploy)
    echo "Deploying to ${ENV}..."
    for SERVICE in api worker beat; do
      aws ecs update-service \
        --cluster homescout-${ENV} \
        --service ${SERVICE} \
        --force-new-deployment \
        --no-cli-pager
      echo "Deployed: ${SERVICE}"
    done
    echo "Waiting for API stability..."
    aws ecs wait services-stable --cluster homescout-${ENV} --services api
    echo "Deploy complete."
    ;;

  migrate)
    echo "Running migrations on ${ENV}..."
    TASK_ARN=$(aws ecs run-task \
      --cluster homescout-${ENV} \
      --task-definition homescout-${ENV}-api \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=homescout-${ENV}-private-*" --query 'Subnets[*].SubnetId' --output text | tr '\t' ','),assignPublicIp=DISABLED}" \
      --overrides '{"containerOverrides":[{"name":"api","environment":[{"name":"SERVICE_TYPE","value":"migrate"}]}]}' \
      --query 'tasks[0].taskArn' \
      --output text)
    echo "Migration task: ${TASK_ARN}"
    aws ecs wait tasks-stopped --cluster homescout-${ENV} --tasks ${TASK_ARN}
    echo "Migrations complete."
    ;;

  status)
    echo "ECS services in homescout-${ENV}:"
    aws ecs describe-services \
      --cluster homescout-${ENV} \
      --services api worker beat \
      --query 'services[].{name:serviceName,status:status,desired:desiredCount,running:runningCount,pending:pendingCount}' \
      --output table
    ;;

  logs)
    echo "Tailing logs for homescout-${ENV}/api..."
    aws logs tail /ecs/homescout-${ENV}/api --follow --since 5m
    ;;

  tf-plan)
    cd infra
    terraform init -backend-config="key=infra/${ENV}/terraform.tfstate"
    terraform plan -var-file=environments/${ENV}.tfvars
    ;;

  tf-apply)
    cd infra
    terraform init -backend-config="key=infra/${ENV}/terraform.tfstate"
    terraform apply -var-file=environments/${ENV}.tfvars
    ;;

  help|*)
    usage
    ;;
esac
```

**Step 2: Make executable and commit**

```bash
chmod +x scripts/deploy.sh
git add scripts/deploy.sh
git commit -m "feat: add deployment helper script"
```

---

### Task 15: Frontend Vercel Configuration

Configure Vercel for multi-environment deployment.

**Files:**
- Create: `frontend/vercel.json`
- Create: `frontend/.env.production` (template only — actual values set in Vercel dashboard)

**Step 1: Create vercel.json**

Create `frontend/vercel.json`:

```json
{
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "installCommand": "npm ci",
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" }
      ]
    }
  ]
}
```

**Step 2: Create env template**

Create `frontend/.env.production`:

```bash
# These values are set per-environment in the Vercel dashboard.
# This file serves as documentation only.
#
# Dev:  NEXT_PUBLIC_API_URL=https://api-dev.homescout.app
# QA:   NEXT_PUBLIC_API_URL=https://api-qa.homescout.app
# Prod: NEXT_PUBLIC_API_URL=https://api.homescout.app
#
# NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY
# are also set per-environment in Vercel.
```

**Step 3: Commit**

```bash
git add frontend/vercel.json frontend/.env.production
git commit -m "feat: add Vercel config and env template for multi-environment frontend"
```

---

### Task 16: Update CORS for Multi-Environment

The backend currently hardcodes `localhost:3000`. Update to support environment-specific frontend URLs.

**Files:**
- Modify: `backend/app/main.py:76-83` (CORS configuration)

**Step 1: Update CORS in main.py**

In `backend/app/main.py`, replace lines 75-83:

```python
# Configure CORS (added last = runs first = wraps all responses with CORS headers)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

With:

```python
# Configure CORS (added last = runs first = wraps all responses with CORS headers)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
cors_origins = [frontend_url]
if "localhost" not in frontend_url:
    # In deployed environments, also allow localhost for development
    cors_origins.append("http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Step 2: Run backend tests**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v --tb=short
```
Expected: All tests pass.

**Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "fix: update CORS to support multi-environment frontend URLs"
```

---

### Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Backend Dockerfile | `backend/Dockerfile`, `docker-entrypoint.sh`, `.dockerignore` |
| 2 | Terraform state backend | `infra/bootstrap/` |
| 3 | Terraform ECR module | `infra/modules/ecr/` |
| 4 | Terraform networking module | `infra/modules/networking/` |
| 5 | Terraform RDS module | `infra/modules/rds/` |
| 6 | Terraform ElastiCache module | `infra/modules/elasticache/` |
| 7 | Terraform ALB module | `infra/modules/alb/` |
| 8 | Terraform ECS module | `infra/modules/ecs/` |
| 9 | Terraform root config + tfvars | `infra/main.tf`, `infra/environments/` |
| 10 | GitHub Actions CI workflow | `.github/workflows/ci.yml` |
| 11 | GitHub Actions deploy workflow | `.github/workflows/deploy-backend.yml` |
| 12 | CloudWatch monitoring alarms | `infra/modules/monitoring/` |
| 13 | Structured JSON logging | `backend/app/logging_config.py` |
| 14 | Deploy helper script | `scripts/deploy.sh` |
| 15 | Vercel frontend configuration | `frontend/vercel.json` |
| 16 | Multi-environment CORS | `backend/app/main.py` |

### First Deploy Checklist (after all tasks)

1. Run `infra/bootstrap/` to create S3 state bucket
2. Create ACM certificate for `*.homescout.app` in AWS
3. Run `terraform apply -var-file=environments/dev.tfvars` for dev environment
4. Populate `homescout/dev/secrets` in AWS Secrets Manager
5. Build and push Docker image to ECR
6. Run `scripts/deploy.sh migrate dev`
7. Run `scripts/deploy.sh deploy dev`
8. Create Route53 record pointing `api-dev.homescout.app` to ALB
9. Connect Vercel to GitHub repo, set environment variables
10. Verify: `curl https://api-dev.homescout.app/health`
