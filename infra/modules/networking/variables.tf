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
