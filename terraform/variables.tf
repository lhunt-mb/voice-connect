variable "aws_region" {
  description = "AWS region for DynamoDB and Lambda (can differ from Nova 2 region)"
  type        = string
  default     = "ap-southeast-2"
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be dev, test, or prod"
  }
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "voice-openai-connect"
}

# Networking
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["ap-southeast-2a", "ap-southeast-2b"]
}

# ECS Configuration
variable "gateway_image_tag" {
  description = "Docker image tag for gateway service"
  type        = string
  default     = "latest"
}

variable "gateway_cpu" {
  description = "CPU units for gateway service (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "gateway_memory_mib" {
  description = "Memory for gateway service in MiB"
  type        = number
  default     = 1024
}

variable "gateway_desired_count" {
  description = "Desired number of gateway tasks"
  type        = number
  default     = 2
}

variable "gateway_min_capacity" {
  description = "Minimum number of gateway tasks for autoscaling"
  type        = number
  default     = 1
}

variable "gateway_max_capacity" {
  description = "Maximum number of gateway tasks for autoscaling"
  type        = number
  default     = 10
}

# DynamoDB Configuration
variable "dynamodb_table_name" {
  description = "Name of DynamoDB table for handover tokens"
  type        = string
  default     = "HandoverTokens"
}

variable "token_ttl_seconds" {
  description = "TTL for handover tokens in seconds"
  type        = number
  default     = 600
}

# Lambda Configuration
variable "lambda_image_tag" {
  description = "Docker image tag for Lambda function"
  type        = string
  default     = "latest"
}

variable "lambda_memory_mib" {
  description = "Memory for Lambda function in MiB"
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

# Secrets Configuration
variable "twilio_account_sid" {
  description = "Twilio Account SID"
  type        = string
  sensitive   = true
}

variable "twilio_auth_token" {
  description = "Twilio Auth Token"
  type        = string
  sensitive   = true
}

variable "twilio_phone_number" {
  description = "Twilio phone number"
  type        = string
}

variable "voice_provider" {
  description = "Voice provider: openai or nova"
  type        = string
  validation {
    condition     = contains(["openai", "nova"], var.voice_provider)
    error_message = "Voice provider must be openai or nova"
  }
}

variable "openai_api_key" {
  description = "OpenAI API key (required if voice_provider is openai)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_realtime_model" {
  description = "OpenAI Realtime model"
  type        = string
  default     = "gpt-4o-realtime-preview-2024-12-17"
}

variable "openai_voice" {
  description = "OpenAI voice (alloy, echo, fable, onyx, nova, shimmer)"
  type        = string
  default     = "alloy"
}

variable "nova_region" {
  description = "AWS region for Nova 2 Sonic (us-east-1, eu-north-1, ap-northeast-1)"
  type        = string
  default     = "us-east-1"
  validation {
    condition     = contains(["us-east-1", "eu-north-1", "ap-northeast-1"], var.nova_region)
    error_message = "Nova region must be us-east-1, eu-north-1, or ap-northeast-1"
  }
}

variable "connect_phone_number" {
  description = "Amazon Connect phone number for escalation"
  type        = string
}

variable "connect_instance_id" {
  description = "Amazon Connect instance ID"
  type        = string
}

variable "hubspot_access_token" {
  description = "HubSpot access token (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "enable_hubspot" {
  description = "Enable HubSpot integration"
  type        = bool
  default     = true
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], var.log_level)
    error_message = "Log level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
  }
}

# SSL Certificate
variable "certificate_arn" {
  description = "ARN of ACM certificate for ALB (required for HTTPS)"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Custom domain name for the service (optional)"
  type        = string
  default     = ""
}

# Bedrock Configuration
variable "enable_bedrock_access" {
  description = "Enable Bedrock access for Nova 2 (required if voice_provider is nova)"
  type        = bool
  default     = false
}

# Knowledge Base Configuration
variable "kb_region" {
  description = "AWS region for Bedrock Knowledge Base (us-east-1, us-west-2, eu-central-1)"
  type        = string
  default     = "us-east-1"
}

variable "enable_kb_tools" {
  description = "Enable Knowledge Base tools for voice providers"
  type        = bool
  default     = false
}

variable "airtable_api_token" {
  description = "Airtable API token for ingestion (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "airtable_base_id" {
  description = "Airtable base ID (e.g., appnM3j6FvK8goI8i)"
  type        = string
  default     = ""
}

variable "admin_api_key" {
  description = "Admin API key for ingestion endpoints"
  type        = string
  sensitive   = true
  default     = ""
}

# Monitoring
variable "enable_container_insights" {
  description = "Enable CloudWatch Container Insights for ECS"
  type        = bool
  default     = true
}

variable "alarm_email" {
  description = "Email address for CloudWatch alarms"
  type        = string
  default     = ""
}

# Tags
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
