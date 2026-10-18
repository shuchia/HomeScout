environment          = "prod"
vpc_cidr             = "10.2.0.0/16"
enable_redundant_nat = false # Single NAT for now (cost saving)
frontend_url         = "https://snugd.ai"
alert_from_email     = "alerts@snugd.ai"
log_level            = "INFO"
use_floorplan_search = "true" # Same as QA; the frontend flag is set separately in Vercel

# CloudWatch alarm notifications (SNS email subscription). Empty = alarms
# exist but notify nobody. Set before launch.
alert_email = ""

# Initial image (see qa.tfvars for the same lifecycle-ignore rationale).
# docs/prod-standup.md retags the current QA image as :prod-latest before the
# first apply so the services have something to pull.
image_tag = "prod-latest"

# RDS — same as QA for now, scale up when ready for real launch.
# Restored from a manual QA snapshot on first create so prod starts with the
# live corpus, market configs and alembic head (see docs/prod-standup.md).
# Ignored after create. 20 GB matches the QA snapshot — the old 50 GB was only
# required by the stale 2026-05-04 snugd-prod-final snapshot.
rds_snapshot_identifier = "snugd-qa-prod-bootstrap"
rds_engine_version      = "16" # major only — the QA snapshot is on a newer minor than 16.6
rds_instance_class      = "db.t4g.micro"
rds_allocated_storage   = 20
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
# Prod scrapes on its own schedule. Without it decay pushes every listing
# below the freshness floor (40) in ~4 weeks and search goes empty.
# Exactly one beat — two double every scheduled scrape.
beat_desired_count = 1

# ACM — wildcard cert *.snugd.ai (shared across dev/qa/prod)
certificate_arn = "arn:aws:acm:us-east-1:453636587892:certificate/7025b517-dbe4-4294-8d90-aaa3170d74de"
