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
      Project     = "snugd"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# --- Secrets Manager (application secrets — populated manually) ---
resource "aws_secretsmanager_secret" "app_secrets" {
  name = "snugd/${var.environment}/secrets"
}

# --- Modules ---
module "ecr" {
  source          = "./modules/ecr"
  repository_name = "snugd-backend"
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
