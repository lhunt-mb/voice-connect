# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda" {
  name              = local.lambda_log_group
  retention_in_days = var.environment == "prod" ? 90 : 30
  kms_key_id        = aws_kms_key.logs.arn

  tags = local.common_tags
}

# Lambda Function for Amazon Connect Token Lookup
resource "aws_lambda_function" "connect_lookup" {
  function_name = local.lambda_function_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.lambda_memory_mib

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = local.dynamodb_table_name
      LOG_LEVEL           = var.log_level
    }
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  tracing_config {
    mode = "Active"
  }

  tags = local.common_tags

  depends_on = [
    aws_iam_role_policy.lambda_logs,
    aws_iam_role_policy.lambda_dynamodb,
    aws_cloudwatch_log_group.lambda
  ]
}

# Security Group for Lambda
resource "aws_security_group" "lambda" {
  name_prefix = "${local.name_prefix}-lambda-"
  description = "Security group for Lambda function"
  vpc_id      = aws_vpc.main.id

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-lambda-sg"
    }
  )

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_egress_rule" "lambda_all" {
  security_group_id = aws_security_group.lambda.id
  description       = "Allow all outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# Lambda Alias for stable invocation
resource "aws_lambda_alias" "connect_lookup" {
  name             = var.environment
  description      = "Alias for ${var.environment} environment"
  function_name    = aws_lambda_function.connect_lookup.arn
  function_version = "$LATEST"
}

# Lambda Permission for Amazon Connect
resource "aws_lambda_permission" "connect" {
  statement_id  = "AllowExecutionFromConnect"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.connect_lookup.function_name
  principal     = "connect.amazonaws.com"
  source_arn    = "arn:aws:connect:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${var.connect_instance_id}/*"
}

# CloudWatch Alarms for Lambda
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count = var.alarm_email != "" ? 1 : 0

  alarm_name          = "${local.lambda_function_name}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Lambda function error rate is too high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.connect_lookup.function_name
  }

  alarm_actions = [aws_sns_topic.alarms[0].arn]

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  count = var.alarm_email != "" ? 1 : 0

  alarm_name          = "${local.lambda_function_name}-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = var.lambda_timeout_seconds * 1000 * 0.8 # 80% of timeout
  alarm_description   = "Lambda function duration is approaching timeout"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.connect_lookup.function_name
  }

  alarm_actions = [aws_sns_topic.alarms[0].arn]

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  count = var.alarm_email != "" ? 1 : 0

  alarm_name          = "${local.lambda_function_name}-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Lambda function is being throttled"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.connect_lookup.function_name
  }

  alarm_actions = [aws_sns_topic.alarms[0].arn]

  tags = local.common_tags
}
