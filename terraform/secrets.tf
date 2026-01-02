# Secrets Manager for application secrets
resource "aws_secretsmanager_secret" "app_secrets" {
  name_prefix             = "${local.app_secrets_name}-"
  description             = "Application secrets for voice-openai-connect"
  recovery_window_in_days = var.environment == "prod" ? 30 : 7
  kms_key_id              = aws_kms_key.secrets.arn

  tags = merge(
    local.common_tags,
    {
      Name = local.app_secrets_name
    }
  )
}

# Store secrets as JSON
resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    # Twilio
    TWILIO_ACCOUNT_SID  = var.twilio_account_sid
    TWILIO_AUTH_TOKEN   = var.twilio_auth_token
    TWILIO_PHONE_NUMBER = var.twilio_phone_number

    # Voice Provider
    VOICE_PROVIDER = var.voice_provider

    # OpenAI (conditionally included)
    OPENAI_API_KEY        = var.voice_provider == "openai" ? var.openai_api_key : ""
    OPENAI_REALTIME_MODEL = var.openai_realtime_model
    OPENAI_VOICE          = var.openai_voice

    # Nova 2
    NOVA_REGION = var.nova_region

    # Amazon Connect
    CONNECT_PHONE_NUMBER = var.connect_phone_number
    CONNECT_INSTANCE_ID  = var.connect_instance_id

    # HubSpot
    HUBSPOT_ACCESS_TOKEN = var.enable_hubspot ? var.hubspot_access_token : ""
    ENABLE_HUBSPOT       = var.enable_hubspot ? "true" : "false"

    # DynamoDB
    DYNAMODB_TABLE_NAME = local.dynamodb_table_name
    AWS_REGION          = var.aws_region

    # Token Configuration
    TOKEN_TTL_SECONDS = tostring(var.token_ttl_seconds)
    TOKEN_LENGTH      = "10"

    # Logging
    LOG_LEVEL = var.log_level

    # Airtable (for Knowledge Base ingestion)
    AIRTABLE_API_TOKEN = var.airtable_api_token
    AIRTABLE_BASE_ID   = var.airtable_base_id

    # Admin API Key (for ingestion endpoints)
    ADMIN_API_KEY = var.admin_api_key

    # Langfuse Observability
    LANGFUSE_ENABLED     = var.langfuse_enabled ? "true" : "false"
    LANGFUSE_PUBLIC_KEY  = var.langfuse_public_key
    LANGFUSE_SECRET_KEY  = var.langfuse_secret_key
    LANGFUSE_HOST        = var.langfuse_host
    LANGFUSE_ENVIRONMENT = var.environment
    LANGFUSE_SAMPLE_RATE = tostring(var.langfuse_sample_rate)
  })
}

# KMS Key for Secrets Manager encryption
resource "aws_kms_key" "secrets" {
  description             = "KMS key for Secrets Manager encryption"
  deletion_window_in_days = var.environment == "prod" ? 30 : 7
  enable_key_rotation     = true

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-secrets-kms"
    }
  )
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${local.name_prefix}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}
