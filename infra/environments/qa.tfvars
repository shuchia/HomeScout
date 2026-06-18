environment          = "qa"
vpc_cidr             = "10.1.0.0/16"
enable_redundant_nat = false
frontend_url         = "https://qa.snugd.ai"
log_level            = "INFO"

# Initial image. CI pushes :qa-latest alongside each :qa-{sha} so this
# stays pullable. Subsequent revisions belong to CI — the ECS module
# uses lifecycle.ignore_changes on container_definitions + the service's
# task_definition pointer so terraform doesn't fight the deploy pipeline.
image_tag            = "qa-latest"

# RDS
rds_instance_class      = "db.t4g.micro"
rds_allocated_storage   = 20
rds_multi_az            = false
rds_backup_retention    = 1
rds_deletion_protection = false

# Redis
redis_node_type = "cache.t4g.micro"
redis_num_nodes = 1

# ECS
api_cpu              = 256
api_memory           = 512
api_desired_count    = 1
worker_cpu           = 256
worker_memory        = 512
worker_desired_count = 1
beat_desired_count   = 1 # QA runs scheduled scraping

# ACM — wildcard cert *.snugd.ai (shared across dev/qa/prod)
certificate_arn = "arn:aws:acm:us-east-1:453636587892:certificate/7025b517-dbe4-4294-8d90-aaa3170d74de"
