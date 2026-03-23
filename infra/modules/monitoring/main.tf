# --- SNS Topic for Alerts ---
resource "aws_sns_topic" "alerts" {
  count = var.environment == "prod" ? 1 : 0
  name  = "snugd-${var.environment}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.environment == "prod" && var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- API 5xx Error Rate ---
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "snugd-${var.environment}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 5
  period              = 300
  statistic           = "Sum"
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    TargetGroup  = var.target_group_arn_suffix
    LoadBalancer = var.alb_arn_suffix
  }
}

# --- API Latency p95 ---
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "snugd-${var.environment}-api-latency-p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 3
  period              = 300
  extended_statistic  = "p95"
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    TargetGroup  = var.target_group_arn_suffix
    LoadBalancer = var.alb_arn_suffix
  }
}

# --- RDS CPU ---
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "snugd-${var.environment}-rds-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 80
  period              = 600
  statistic           = "Average"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }
}

# --- RDS Free Storage ---
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  count               = var.environment == "prod" ? 1 : 0
  alarm_name          = "snugd-${var.environment}-rds-low-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  threshold           = 5368709120 # 5GB in bytes
  period              = 300
  statistic           = "Average"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  alarm_actions       = [aws_sns_topic.alerts[0].arn]

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }
}
