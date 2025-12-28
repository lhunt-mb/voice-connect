#!/bin/bash
set -e

# Create DynamoDB table for handover tokens
# Usage: ./scripts/create_dynamodb_table.sh

TABLE_NAME="HandoverTokens"
REGION="ap-southeast-2"

echo "Creating DynamoDB table: $TABLE_NAME"

aws dynamodb create-table \
  --table-name "$TABLE_NAME" \
  --attribute-definitions AttributeName=token,AttributeType=S \
  --key-schema AttributeName=token,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION"

echo "Waiting for table to be active..."
aws dynamodb wait table-exists --table-name "$TABLE_NAME" --region "$REGION"

echo "Enabling TTL on expires_at attribute..."
aws dynamodb update-time-to-live \
  --table-name "$TABLE_NAME" \
  --time-to-live-specification "Enabled=true,AttributeName=expires_at" \
  --region "$REGION"

echo "DynamoDB table created successfully!"
echo "Table name: $TABLE_NAME"
echo "Region: $REGION"
echo "Billing mode: PAY_PER_REQUEST"
echo "TTL enabled: expires_at"
