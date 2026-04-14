environment          = "prod"
vpc_cidr             = "10.2.0.0/16"
enable_redundant_nat = false # Single NAT for now (cost saving)
frontend_url         = "https://snugd.ai"
log_level            = "INFO"

# RDS — same as QA for now, scale up when ready for real launch
rds_instance_class      = "db.t4g.micro"
rds_allocated_storage   = 50 # Can't shrink RDS storage — was created at 50GB
rds_multi_az            = false
rds_backup_retention    = 1
rds_deletion_protection = false

# Redis
redis_node_type = "cache.t4g.micro"
redis_num_nodes = 1

# ECS — single instance, same as QA
api_cpu              = 256
api_memory           = 512
api_desired_count    = 1
worker_cpu           = 256
worker_memory        = 512
worker_desired_count = 1
beat_desired_count   = 0 # No scraping in prod yet — enable at launch

# ACM — wildcard cert *.snugd.ai (shared across dev/qa/prod)
certificate_arn = "arn:aws:acm:us-east-1:453636587892:certificate/7025b517-dbe4-4294-8d90-aaa3170d74de"
