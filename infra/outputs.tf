output "alb_dns_name" {
  value       = module.alb.dns_name
  description = "ALB DNS name — point your Route53 record here"
}

output "alb_zone_id" {
  value       = module.alb.zone_id
  description = "ALB hosted zone ID — needed for Route53 alias records"
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

output "private_subnet_ids" {
  value       = module.networking.private_subnet_ids
  description = "Private subnet IDs — needed for GitHub environment secrets"
}

output "ecs_security_group_id" {
  value       = module.networking.ecs_security_group_id
  description = "ECS security group ID — needed for GitHub environment secrets"
}
