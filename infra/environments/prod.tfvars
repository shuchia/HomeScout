environment          = "prod"
vpc_cidr             = "10.2.0.0/16"
enable_redundant_nat = true
frontend_url         = "https://snugd.ai"
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
