locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Common tags
  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    },
    var.additional_tags
  )

  # Networking
  azs             = var.availability_zones
  public_subnets  = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k)]
  private_subnets = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k + 10)]

  # Service names
  gateway_service_name = "${local.name_prefix}-gateway"
  lambda_function_name = "${local.name_prefix}-connect-lookup"

  # ECR repositories
  gateway_ecr_repo = "${var.project_name}/gateway"
  lambda_ecr_repo  = "${var.project_name}/connect-lambda"

  # DynamoDB
  dynamodb_table_name = "${local.name_prefix}-${var.dynamodb_table_name}"

  # CloudWatch Log Groups
  gateway_log_group = "/ecs/${local.gateway_service_name}"
  lambda_log_group  = "/aws/lambda/${local.lambda_function_name}"

  # Secrets Manager secret name
  app_secrets_name = "${local.name_prefix}-secrets"

  # Enable HTTPS if certificate is provided
  enable_https = var.certificate_arn != ""

  # ALB listener port
  alb_listener_port = local.enable_https ? 443 : 80
  alb_protocol      = local.enable_https ? "HTTPS" : "HTTP"
}
