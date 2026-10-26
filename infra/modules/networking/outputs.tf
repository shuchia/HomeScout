output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "redis_security_group_id" {
  value = aws_security_group.redis.id
}

# Where ECS tasks run: private behind the NAT, or public with their own IP
# when there is no NAT (the ECS security group still only admits the ALB).
output "ecs_subnet_ids" {
  value = var.enable_nat ? aws_subnet.private[*].id : aws_subnet.public[*].id
}

output "ecs_assign_public_ip" {
  value = !var.enable_nat
}
