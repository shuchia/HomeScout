output "alb_dns_name" {
  value       = module.alb.dns_name
  description = "ALB DNS name — point your Route53 record here"
}

output "ecr_repository_url" {
  value       = module.ecr.repository_url
  description = "ECR repository URL for docker push"
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "redis_endpoint" {
  value = module.elasticache.endpoint
}
