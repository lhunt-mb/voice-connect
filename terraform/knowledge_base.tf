# ==============================================================================
# Amazon Bedrock Knowledge Base Infrastructure
# ==============================================================================
#
# This module provisions:
# - S3 bucket for knowledge base documents (Airtable data)
# - OpenSearch Serverless collection for vector storage
# - Bedrock Knowledge Base with data source pointing to S3
# - IAM roles for Bedrock to access S3 and OpenSearch
#
# Document organization in S3:
# - {prefix}/products/     - Legal service products with eligibility
# - {prefix}/needs/        - Client needs mapped to products
# - {prefix}/providers/    - Lawyer profiles
# - {prefix}/guardrails/   - Compliance rules and tone guidelines
#
# ==============================================================================

# ------------------------------------------------------------------------------
# S3 Bucket for Knowledge Base Documents
# ------------------------------------------------------------------------------

resource "aws_s3_bucket" "kb_documents" {
  bucket_prefix = "${local.name_prefix}-kb-docs-"

  tags = merge(
    local.common_tags,
    {
      Name        = "${local.name_prefix}-kb-documents"
      Description = "Knowledge Base documents from Airtable"
    }
  )
}

# Enable versioning for document history tracking
resource "aws_s3_bucket_versioning" "kb_documents" {
  bucket = aws_s3_bucket.kb_documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "kb_documents" {
  bucket = aws_s3_bucket.kb_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "kb_documents" {
  bucket = aws_s3_bucket.kb_documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle policy to clean up old versions
resource "aws_s3_bucket_lifecycle_configuration" "kb_documents" {
  bucket = aws_s3_bucket.kb_documents.id

  rule {
    id     = "cleanup-old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ------------------------------------------------------------------------------
# OpenSearch Serverless for Vector Storage
# ------------------------------------------------------------------------------

# Encryption policy for OpenSearch Serverless collection
resource "aws_opensearchserverless_security_policy" "kb_encryption" {
  name        = "${var.project_name}-${var.environment}-kb-enc"
  description = "Encryption policy for Knowledge Base collection"
  type        = "encryption"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource = [
          "collection/${var.project_name}-${var.environment}-kb-vec"
        ]
      }
    ]
    AWSOwnedKey = true
  })
}

# Network policy for OpenSearch Serverless collection
resource "aws_opensearchserverless_security_policy" "kb_network" {
  name        = "${var.project_name}-${var.environment}-kb-net"
  description = "Network policy for Knowledge Base collection"
  type        = "network"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.project_name}-${var.environment}-kb-vec"
          ]
        },
        {
          ResourceType = "dashboard"
          Resource = [
            "collection/${var.project_name}-${var.environment}-kb-vec"
          ]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# OpenSearch Serverless collection for vector storage
resource "aws_opensearchserverless_collection" "kb" {
  name = "${var.project_name}-${var.environment}-kb-vec"
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.kb_encryption,
    aws_opensearchserverless_security_policy.kb_network
  ]

  tags = merge(
    local.common_tags,
    {
      Name        = "${local.name_prefix}-kb-collection"
      Description = "Vector storage for Knowledge Base"
    }
  )
}

# Data access policy for OpenSearch Serverless
resource "aws_opensearchserverless_access_policy" "kb_data_access" {
  name        = "${var.project_name}-${var.environment}-kb-data"
  description = "Data access policy for Knowledge Base collection"
  type        = "data"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.project_name}-${var.environment}-kb-vec"
          ]
          Permission = [
            "aoss:DescribeCollectionItems",
            "aoss:CreateCollectionItems",
            "aoss:UpdateCollectionItems"
          ]
        },
        {
          ResourceType = "index"
          Resource = [
            "index/${var.project_name}-${var.environment}-kb-vec/*"
          ]
          Permission = [
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:CreateIndex"
          ]
        }
      ]
      Principal = [
        aws_iam_role.bedrock_kb.arn
      ]
    }
  ])

  depends_on = [
    aws_opensearchserverless_collection.kb
  ]
}

# ------------------------------------------------------------------------------
# IAM Role for Bedrock Knowledge Base
# ------------------------------------------------------------------------------

# IAM role for Bedrock to access S3 and OpenSearch
resource "aws_iam_role" "bedrock_kb" {
  name_prefix = "${local.name_prefix}-bedrock-kb-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock:${var.kb_region}:${data.aws_caller_identity.current.account_id}:knowledge-base/*"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Policy for Bedrock to access S3 documents
resource "aws_iam_role_policy" "bedrock_kb_s3" {
  name_prefix = "${local.name_prefix}-bedrock-kb-s3-"
  role        = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.kb_documents.arn,
          "${aws_s3_bucket.kb_documents.arn}/*"
        ]
      }
    ]
  })
}

# Policy for Bedrock to access OpenSearch Serverless
resource "aws_iam_role_policy" "bedrock_kb_aoss" {
  name_prefix = "${local.name_prefix}-bedrock-kb-aoss-"
  role        = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = aws_opensearchserverless_collection.kb.arn
      }
    ]
  })
}

# Policy for Bedrock to invoke foundation models for embeddings
resource "aws_iam_role_policy" "bedrock_kb_models" {
  name_prefix = "${local.name_prefix}-bedrock-kb-models-"
  role        = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          # Titan Embeddings V2 for vector generation
          "arn:aws:bedrock:${var.kb_region}::foundation-model/amazon.titan-embed-text-v2:0",
          # Claude 3 Haiku for RetrieveAndGenerate
          "arn:aws:bedrock:${var.kb_region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
        ]
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# Bedrock Knowledge Base
# Note: Index will be created automatically during first data source sync
# ------------------------------------------------------------------------------

resource "aws_bedrockagent_knowledge_base" "policies" {
  name        = "${local.name_prefix}-policies"
  description = "Legal policies knowledge base from Airtable (products, needs, providers, guardrails)"
  role_arn    = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.kb_region}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.kb.arn
      vector_index_name = "bedrock-kb-default-index"
      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }

  depends_on = [
    aws_opensearchserverless_access_policy.kb_data_access,
    aws_iam_role_policy.bedrock_kb_s3,
    aws_iam_role_policy.bedrock_kb_aoss,
    aws_iam_role_policy.bedrock_kb_models
  ]

  tags = merge(
    local.common_tags,
    {
      Name        = "${local.name_prefix}-kb-policies"
      Description = "Knowledge Base for legal intake triage"
    }
  )
}

# ------------------------------------------------------------------------------
# Bedrock Data Source (S3)
# ------------------------------------------------------------------------------

resource "aws_bedrockagent_data_source" "airtable" {
  name              = "airtable-documents"
  description       = "Airtable data ingested from products, needs, providers, and guardrails tables"
  knowledge_base_id = aws_bedrockagent_knowledge_base.policies.id

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = aws_s3_bucket.kb_documents.arn
      inclusion_prefixes = [
        "airtable-docs/"
      ]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 300
        overlap_percentage = 20
      }
    }
  }
}
