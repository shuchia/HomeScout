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
