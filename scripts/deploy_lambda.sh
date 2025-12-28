#!/bin/bash
set -e

# Deploy Amazon Connect Lambda function
# Usage: ./scripts/deploy_lambda.sh

FUNCTION_NAME="ConnectTokenLookup"
REGION="ap-southeast-2"
ROLE_ARN="arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-connect-role"
DYNAMODB_TABLE="HandoverTokens"

echo "Building Lambda deployment package..."
cd aws/connect_lambda

# Create deployment package
zip -r lambda-package.zip handler.py

echo "Deploying Lambda function: $FUNCTION_NAME"

# Check if function exists
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" 2>/dev/null; then
  echo "Updating existing function..."
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://lambda-package.zip \
    --region "$REGION"

  # Update environment variables
  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "Variables={DYNAMODB_TABLE_NAME=$DYNAMODB_TABLE,AWS_REGION=$REGION}" \
    --region "$REGION"
else
  echo "Creating new function..."
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.12 \
    --role "$ROLE_ARN" \
    --handler handler.lambda_handler \
    --zip-file fileb://lambda-package.zip \
    --timeout 30 \
    --memory-size 256 \
    --environment "Variables={DYNAMODB_TABLE_NAME=$DYNAMODB_TABLE,AWS_REGION=$REGION}" \
    --region "$REGION"
fi

# Clean up
rm lambda-package.zip

echo "Lambda function deployed successfully!"
echo "Function name: $FUNCTION_NAME"
echo "Region: $REGION"
echo ""
echo "Next steps:"
echo "1. Grant Amazon Connect permissions to invoke this Lambda"
echo "2. Add Lambda function to your Connect instance"
echo "3. Configure contact flow to invoke Lambda with token parameter"
