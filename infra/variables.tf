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

variable "beat_desired_count" {
  description = "Desired count for beat service (0 to disable scheduled tasks in dev/qa)"
  type        = number
  default     = 1
}

variable "alert_email" {
  description = "Email for CloudWatch alarm notifications (prod only)"
  type        = string
  default     = ""
}

variable "frontend_url" {
  type = string
}

# The From address on product email (daily alerts, tour reminders).
# alert_tasks.py falls back to a hardcoded "alerts@snugd.app" when this is
# unset, which is what every deployed environment has been sending as — note
# the domain differs from the product's. The chosen domain must be verified in
# Resend (SPF + DKIM) or sends are rejected provider-side, silently.
variable "alert_from_email" {
  type    = string
  default = "alerts@snugd.ai"
}

variable "log_level" {
  type    = string
  default = "INFO"
}

variable "use_floorplan_search" {
  description = "Enable floorplan-aware apartment search. Set per-env in *.tfvars."
  type        = string
  default     = "false"
}

variable "rds_engine_version" {
  description = "Postgres engine version. QA keeps the 16.6 it was created with; prod uses \"16\"."
  type        = string
  default     = "16.6"
}

variable "rds_snapshot_identifier" {
  description = "Snapshot to restore RDS from on first create (null = empty DB). See docs/prod-standup.md."
  type        = string
  default     = null
}
