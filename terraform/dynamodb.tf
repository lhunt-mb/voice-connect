# DynamoDB Table for Handover Tokens
resource "aws_dynamodb_table" "handover_tokens" {
  name           = local.dynamodb_table_name
  billing_mode   = "PAY_PER_REQUEST" # On-demand pricing for variable workloads
  hash_key       = "token"
  stream_enabled = false

  attribute {
    name = "token"
    type = "S"
  }

  # TTL configuration for automatic token expiration
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # Point-in-time recovery for production
  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.dynamodb.arn
  }

  tags = merge(
    local.common_tags,
    {
      Name = local.dynamodb_table_name
    }
  )
}

# KMS Key for DynamoDB encryption
resource "aws_kms_key" "dynamodb" {
  description             = "KMS key for DynamoDB table encryption"
  deletion_window_in_days = var.environment == "prod" ? 30 : 7
  enable_key_rotation     = true

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-dynamodb-kms"
    }
  )
}

resource "aws_kms_alias" "dynamodb" {
  name          = "alias/${local.name_prefix}-dynamodb"
  target_key_id = aws_kms_key.dynamodb.key_id
}
