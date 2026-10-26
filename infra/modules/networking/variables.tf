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

variable "enable_nat" {
  description = "Create a NAT gateway for the private subnets. false = ECS tasks run in the public subnets with public IPs"
  type        = bool
  default     = true
}
