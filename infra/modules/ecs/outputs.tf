output "cluster_id" {
  value = aws_ecs_cluster.main.id
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "api_service_name" {
  value = aws_ecs_service.api.name
}

output "api_task_definition_family" {
  value = aws_ecs_task_definition.api.family
}

output "migration_task_definition_arn" {
  value       = aws_ecs_task_definition.api.arn
  description = "Use with command override SERVICE_TYPE=migrate for Alembic migrations"
}
