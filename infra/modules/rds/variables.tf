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
  default = "snugd"
}

variable "db_username" {
  type    = string
  default = "snugd"
}

# QA was created at 16.6 and auto-minor-upgraded since (16.13 on 2026-10-18).
# The default keeps QA's config byte-identical; prod sets the major only ("16")
# so a restore from a newer QA snapshot isn't read as a downgrade.
variable "engine_version" {
  type    = string
  default = "16.6"
}

# Restore from an existing snapshot instead of creating an empty database.
# Null (the default) creates a fresh instance — QA never sets it. Used to
# bootstrap prod from a current QA snapshot so it starts with the live corpus,
# market configs and alembic head.
variable "snapshot_identifier" {
  type    = string
  default = null
}
