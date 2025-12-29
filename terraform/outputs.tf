# VPC Outputs
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

# ALB Outputs
output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = aws_lb.main.zone_id
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.main.arn
}

output "gateway_endpoint" {
  description = "Full endpoint URL for the gateway service"
  value       = local.enable_https ? "https://${var.domain_name != "" ? var.domain_name : aws_lb.main.dns_name}" : "http://${aws_lb.main.dns_name}"
}

# ECS Outputs
output "ecs_cluster_id" {
  description = "ID of the ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.gateway.name
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.gateway.arn
}

# ECR Outputs
output "ecr_gateway_repository_url" {
  description = "URL of the ECR repository for gateway service"
  value       = aws_ecr_repository.gateway.repository_url
}

output "ecr_lambda_repository_url" {
  description = "URL of the ECR repository for Lambda function"
  value       = aws_ecr_repository.lambda.repository_url
}

# DynamoDB Outputs
output "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.handover_tokens.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table"
  value       = aws_dynamodb_table.handover_tokens.arn
}

# Lambda Outputs
output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.connect_lookup.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.connect_lookup.arn
}

output "lambda_function_qualified_arn" {
  description = "Qualified ARN of the Lambda function (with version/alias)"
  value       = aws_lambda_alias.connect_lookup.arn
}

# Secrets Manager Outputs
output "secrets_manager_secret_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.app_secrets.arn
  sensitive   = true
}

# IAM Outputs
output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_task_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda.arn
}

# Security Group Outputs
output "alb_security_group_id" {
  description = "ID of the ALB security group"
  value       = aws_security_group.alb.id
}

output "ecs_tasks_security_group_id" {
  description = "ID of the ECS tasks security group"
  value       = aws_security_group.ecs_tasks.id
}

output "lambda_security_group_id" {
  description = "ID of the Lambda security group"
  value       = aws_security_group.lambda.id
}

# CloudWatch Outputs
output "gateway_log_group_name" {
  description = "Name of the CloudWatch log group for gateway service"
  value       = aws_cloudwatch_log_group.gateway.name
}

output "lambda_log_group_name" {
  description = "Name of the CloudWatch log group for Lambda function"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "cloudwatch_dashboard_url" {
  description = "URL to the CloudWatch dashboard"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

# SNS Outputs
output "alarm_topic_arn" {
  description = "ARN of the SNS topic for alarms"
  value       = var.alarm_email != "" ? aws_sns_topic.alarms[0].arn : null
}

# Deployment Instructions
output "deployment_instructions" {
  description = "Instructions for deploying the application"
  value       = <<-EOT

  Deployment Steps:

  1. Build and Push Docker Images:

     # Gateway Service
     cd ${path.module}/..
     docker build -t ${aws_ecr_repository.gateway.repository_url}:latest .
     aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.gateway.repository_url}
     docker push ${aws_ecr_repository.gateway.repository_url}:latest

     # Lambda Function
     cd aws/connect_lambda
     docker build -t ${aws_ecr_repository.lambda.repository_url}:latest .
     aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.lambda.repository_url}
     docker push ${aws_ecr_repository.lambda.repository_url}:latest

  2. Update ECS Service (if needed):
     aws ecs update-service --cluster ${aws_ecs_cluster.main.name} --service ${aws_ecs_service.gateway.name} --force-new-deployment --region ${var.aws_region}

  3. Update Lambda Function (if needed):
     aws lambda update-function-code --function-name ${aws_lambda_function.connect_lookup.function_name} --image-uri ${aws_ecr_repository.lambda.repository_url}:latest --region ${var.aws_region}

  4. Configure Twilio:
     - Set webhook URL to: ${local.enable_https ? "https://${var.domain_name != "" ? var.domain_name : aws_lb.main.dns_name}" : "http://${aws_lb.main.dns_name}"}/twilio/voice
     - Set stream URL to: ${local.enable_https ? "wss://${var.domain_name != "" ? var.domain_name : aws_lb.main.dns_name}" : "ws://${aws_lb.main.dns_name}"}/twilio/stream

  5. Configure Amazon Connect:
     - Add Lambda function: ${aws_lambda_alias.connect_lookup.arn}
     - Configure contact flow to capture DTMF token
     - Use Lambda function to retrieve handover context

  6. Monitor:
     - CloudWatch Dashboard: ${aws_cloudwatch_dashboard.main.dashboard_name}
     - Logs: CloudWatch Logs
     - Alarms: ${var.alarm_email != "" ? "Configured to send to ${var.alarm_email}" : "Not configured"}

  EOT
}

# Twilio Configuration
output "twilio_webhook_url" {
  description = "Webhook URL for Twilio voice calls"
  value       = "${local.enable_https ? "https://${var.domain_name != "" ? var.domain_name : aws_lb.main.dns_name}" : "http://${aws_lb.main.dns_name}"}/twilio/voice"
}

output "twilio_stream_url" {
  description = "WebSocket URL for Twilio media streams"
  value       = "${local.enable_https ? "wss://${var.domain_name != "" ? var.domain_name : aws_lb.main.dns_name}" : "ws://${aws_lb.main.dns_name}"}/twilio/stream"
}
