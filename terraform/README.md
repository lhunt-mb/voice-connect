# Voice OpenAI Connect - Terraform Infrastructure

This directory contains Terraform infrastructure as code (IaC) for deploying the Voice OpenAI Connect service to AWS.

> **Default Region**: This infrastructure is configured to deploy to **ap-southeast-2 (Sydney)** by default. The Nova 2 Bedrock region can be configured independently (supports us-east-1, eu-north-1, or ap-northeast-1).

## Architecture Overview

The infrastructure deploys a production-ready, highly available voice AI gateway with the following components:

### Core Services
- **ECS Fargate** - Containerized gateway service (FastAPI WebSocket application)
- **Application Load Balancer** - WebSocket-capable load balancer with HTTPS support
- **DynamoDB** - Token storage with automatic TTL expiration
- **Lambda** - Amazon Connect integration for token validation
- **Secrets Manager** - Secure credential storage
- **ECR** - Container image repositories

### Networking
- **VPC** - Multi-AZ VPC with public and private subnets
- **NAT Gateways** - High availability (multi-AZ in prod, single in non-prod)
- **VPC Endpoints** - Cost-optimized access to AWS services (S3, DynamoDB, ECR, Logs, Secrets Manager)
- **Security Groups** - Least-privilege network access controls
- **Note**: Bedrock access uses NAT Gateway (VPC endpoints don't support cross-region access)

### Observability
- **CloudWatch Logs** - Centralized logging with KMS encryption
- **CloudWatch Metrics** - Service and infrastructure metrics
- **CloudWatch Alarms** - Proactive alerting via SNS
- **CloudWatch Dashboard** - Unified monitoring view
- **VPC Flow Logs** - Network traffic analysis

### Security
- **KMS Encryption** - All data encrypted at rest
- **IAM Roles** - Least-privilege access policies
- **VPC Isolation** - Private subnets for compute resources
- **Security Groups** - Network segmentation
- **Secrets Management** - No hardcoded credentials

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** >= 1.0.0
3. **AWS CLI** configured with credentials
4. **Docker** for building container images
5. **Twilio Account** with voice capabilities
6. **Amazon Connect Instance** configured
7. **OpenAI API Key** (if using OpenAI) or **Bedrock access** (if using Nova)
8. **HubSpot Account** (optional, for CRM integration)

## Quick Start

### 1. Configure Backend (Recommended)

Create a `backend.hcl` file for remote state:

```hcl
bucket         = "your-terraform-state-bucket"
key            = "voice-openai-connect/terraform.tfstate"
region         = "ap-southeast-2"
dynamodb_table = "terraform-state-locking"
encrypt        = true
```

Initialize with backend config:

```bash
terraform init -backend-config=backend.hcl
```

### 2. Configure Variables

Copy the example tfvars file:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

```hcl
# Required variables
environment             = "dev"
aws_region             = "ap-southeast-2"
twilio_account_sid     = "ACxxxxxxxxxxxxxxxxxxxx"
twilio_auth_token      = "your_auth_token"
twilio_phone_number    = "+15551234567"
voice_provider         = "nova"  # or "openai"
connect_phone_number   = "+15551234567"
connect_instance_id    = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

# OpenAI (if voice_provider = "openai")
openai_api_key         = "sk-..."

# Nova (if voice_provider = "nova")
nova_region            = "us-east-1"
enable_bedrock_access  = true

# Optional
alarm_email            = "alerts@example.com"
certificate_arn        = "arn:aws:acm:us-east-1:..."  # For HTTPS
domain_name            = "voice.example.com"  # For custom domain
```

**IMPORTANT**: Never commit `terraform.tfvars` with real credentials! Add it to `.gitignore`.

### 3. Build and Push Docker Images

Before running Terraform, build and push your Docker images to ECR:

```bash
# Create ECR repositories first (Terraform will do this)
terraform apply -target=aws_ecr_repository.gateway -target=aws_ecr_repository.lambda

# Build and push gateway image
cd ..
AWS_REGION=ap-southeast-2
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GATEWAY_ECR="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/voice-openai-connect/gateway"

docker build -t ${GATEWAY_ECR}:latest .
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${GATEWAY_ECR}
docker push ${GATEWAY_ECR}:latest

# Build and push Lambda image
cd aws/connect_lambda
LAMBDA_ECR="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/voice-openai-connect/connect-lambda"

docker build -t ${LAMBDA_ECR}:latest .
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${LAMBDA_ECR}
docker push ${LAMBDA_ECR}:latest
```

### 4. Deploy Infrastructure

```bash
# Validate configuration
terraform validate

# Plan changes
terraform plan -out=tfplan

# Apply infrastructure
terraform apply tfplan
```

### 5. Configure External Services

After deployment, configure Twilio and Amazon Connect:

#### Twilio Configuration

1. Go to Twilio Console → Phone Numbers
2. Select your phone number
3. Configure Voice & Fax:
   - **A Call Comes In**: Webhook
   - **URL**: `https://your-alb-dns/twilio/voice` (from Terraform output `twilio_webhook_url`)
   - **Method**: POST

#### Amazon Connect Configuration

1. Go to Amazon Connect Console → Contact Flows
2. Create a new contact flow
3. Add "Invoke AWS Lambda function" block
4. Select Lambda function: `voice-openai-connect-{env}-connect-lookup`
5. Configure DTMF input to capture 10-digit token
6. Use Lambda response attributes for agent screen pop
7. Route to appropriate queue

## Infrastructure Components

### Networking ([vpc.tf](terraform/vpc.tf))

- **VPC**: 10.0.0.0/16 (configurable)
- **Public Subnets**: 2 AZs for high availability
- **Private Subnets**: 2 AZs for ECS tasks and Lambda
- **NAT Gateways**: Multi-AZ in prod, single in non-prod
- **VPC Endpoints**: Gateway endpoints for S3/DynamoDB, Interface endpoints for ECR/Logs/Secrets Manager

### Compute ([ecs.tf](terraform/ecs.tf), [lambda.tf](terraform/lambda.tf))

- **ECS Cluster**: Fargate launch type
- **ECS Service**: Auto-scaling (1-10 tasks), rolling deployments
- **Lambda Function**: VPC-attached, connects to Amazon Connect

### Storage ([dynamodb.tf](terraform/dynamodb.tf), [ecr.tf](terraform/ecr.tf))

- **DynamoDB**: On-demand billing, TTL enabled, encrypted with KMS
- **ECR**: Lifecycle policies, image scanning, KMS encryption

### Security ([iam.tf](terraform/iam.tf), [secrets.tf](terraform/secrets.tf))

- **IAM Roles**: Separate roles for ECS task, ECS execution, Lambda, VPC Flow Logs
- **Secrets Manager**: All credentials stored securely
- **KMS Keys**: Separate keys for DynamoDB, Secrets, Logs, ECR, SNS

### Networking ([alb.tf](terraform/alb.tf))

- **Application Load Balancer**: Internet-facing, WebSocket support
- **Target Group**: Health checks, sticky sessions
- **Listeners**: HTTP (redirects to HTTPS if cert provided), HTTPS (optional)

### Monitoring ([monitoring.tf](terraform/monitoring.tf))

- **CloudWatch Alarms**: CPU, memory, errors, throttles, unhealthy hosts
- **SNS Topic**: Email notifications
- **Dashboard**: Unified view of service health

## Operations

### Updating the Application

#### Update Gateway Service

```bash
# Build new image
docker build -t ${GATEWAY_ECR}:v1.0.1 .
docker push ${GATEWAY_ECR}:v1.0.1

# Update Terraform variable
echo 'gateway_image_tag = "v1.0.1"' >> terraform.tfvars

# Apply changes
terraform apply

# Or force new deployment without Terraform
aws ecs update-service \
  --cluster voice-openai-connect-{env}-cluster \
  --service voice-openai-connect-{env}-gateway \
  --force-new-deployment \
  --region us-east-1
```

#### Update Lambda Function

```bash
# Build new image
cd aws/connect_lambda
docker build -t ${LAMBDA_ECR}:v1.0.1 .
docker push ${LAMBDA_ECR}:v1.0.1

# Update Lambda
aws lambda update-function-code \
  --function-name voice-openai-connect-{env}-connect-lookup \
  --image-uri ${LAMBDA_ECR}:v1.0.1 \
  --region us-east-1
```

### Scaling

The ECS service auto-scales based on:
- CPU utilization (target: 70%)
- Memory utilization (target: 80%)
- ALB request count (target: 1000 req/target)

Manual scaling:

```bash
aws ecs update-service \
  --cluster voice-openai-connect-{env}-cluster \
  --service voice-openai-connect-{env}-gateway \
  --desired-count 5 \
  --region us-east-1
```

### Logs

Access logs via CloudWatch:

```bash
# ECS logs
aws logs tail /ecs/voice-openai-connect-{env}-gateway --follow

# Lambda logs
aws logs tail /aws/lambda/voice-openai-connect-{env}-connect-lookup --follow

# VPC Flow Logs
aws logs tail /aws/vpc/voice-openai-connect-{env}-flow-logs --follow
```

### Monitoring

View CloudWatch Dashboard:

```bash
open "https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=voice-openai-connect-{env}-dashboard"
```

### Secrets Rotation

Update secrets in Secrets Manager:

```bash
aws secretsmanager update-secret \
  --secret-id voice-openai-connect-{env}-secrets \
  --secret-string '{
    "TWILIO_ACCOUNT_SID": "new_value",
    "TWILIO_AUTH_TOKEN": "new_value",
    ...
  }' \
  --region ap-southeast-2

# Restart ECS tasks to pick up new secrets
aws ecs update-service \
  --cluster voice-openai-connect-{env}-cluster \
  --service voice-openai-connect-{env}-gateway \
  --force-new-deployment \
  --region ap-southeast-2
```

## Cost Optimization

### Non-Production Environments

- Single NAT Gateway (vs multi-AZ)
- Lower ECS task count
- Shorter log retention
- Reduced KMS key deletion window

### Production Recommendations

1. **Reserved Capacity**: Consider Savings Plans for steady-state workloads
2. **S3 Lifecycle**: Configure ALB access logs with lifecycle policies
3. **DynamoDB**: On-demand billing for variable traffic
4. **NAT Gateway**: Use VPC endpoints where possible to reduce NAT costs
5. **CloudWatch Logs**: Set appropriate retention periods

### Estimated Monthly Costs (ap-southeast-2)

#### Development Environment
- **ECS Fargate** (2 tasks, 0.5 vCPU, 1GB): ~$33
- **ALB**: ~$23
- **NAT Gateway** (single): ~$38
- **DynamoDB** (on-demand, light usage): ~$5
- **Lambda** (1M invocations): ~$5
- **VPC Endpoints**: ~$16
- **CloudWatch Logs** (10GB/month): ~$5
- **Total**: ~$125/month

#### Production Environment
- **ECS Fargate** (avg 4 tasks, 0.5 vCPU, 1GB): ~$66
- **ALB**: ~$28
- **NAT Gateway** (multi-AZ): ~$76
- **DynamoDB** (on-demand, moderate usage): ~$22
- **Lambda** (10M invocations): ~$22
- **VPC Endpoints**: ~$16
- **CloudWatch Logs** (50GB/month): ~$28
- **Total**: ~$258/month

*Note: Costs shown are for ap-southeast-2 (Sydney) region, approximately 10% higher than us-east-1. Costs vary based on usage and data transfer. Add costs for Twilio, OpenAI/Bedrock, and HubSpot.*

## Security Best Practices

✅ **Encryption**: All data encrypted at rest with KMS
✅ **Network Isolation**: Private subnets for compute, security groups with least privilege
✅ **Secrets Management**: No hardcoded credentials, Secrets Manager integration
✅ **IAM Roles**: Task-specific roles with minimal permissions
✅ **VPC Endpoints**: Reduced internet exposure for AWS services
✅ **Logging**: Comprehensive CloudWatch logging with encryption
✅ **Monitoring**: Proactive alerting for security events
✅ **Image Scanning**: ECR vulnerability scanning enabled

## Troubleshooting

### ECS Tasks Not Starting

```bash
# Check service events
aws ecs describe-services \
  --cluster voice-openai-connect-{env}-cluster \
  --services voice-openai-connect-{env}-gateway

# Check task logs
aws logs tail /ecs/voice-openai-connect-{env}-gateway --follow

# Check task execution role
aws iam get-role --role-name voice-openai-connect-{env}-ecs-exec
```

### ALB Health Checks Failing

```bash
# Check target health
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn>

# Check security group rules
aws ec2 describe-security-groups \
  --group-ids <ecs-tasks-sg-id>
```

### Lambda Errors

```bash
# View Lambda logs
aws logs tail /aws/lambda/voice-openai-connect-{env}-connect-lookup --follow

# Check Lambda configuration
aws lambda get-function \
  --function-name voice-openai-connect-{env}-connect-lookup

# Test Lambda manually
aws lambda invoke \
  --function-name voice-openai-connect-{env}-connect-lookup \
  --payload '{"token":"1234567890"}' \
  response.json
```

### DynamoDB Throttling

```bash
# Check metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ReadThrottleEvents \
  --dimensions Name=TableName,Value=voice-openai-connect-{env}-HandoverTokens \
  --statistics Sum \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600

# DynamoDB is using on-demand billing mode, so throttling should be rare
# If it occurs, check for hot partition keys or inefficient queries
```

## Disaster Recovery

### Backup Strategy

- **DynamoDB**: Point-in-time recovery enabled in prod
- **Secrets Manager**: 30-day recovery window in prod
- **Terraform State**: Version-controlled in S3 with DynamoDB locking

### Recovery Procedures

#### Complete Environment Loss

```bash
# Terraform will recreate all infrastructure
terraform apply

# Re-push Docker images
# Re-configure Twilio webhooks
# Re-configure Amazon Connect
```

#### Data Loss (DynamoDB)

```bash
# Restore from point-in-time (production only)
aws dynamodb restore-table-to-point-in-time \
  --source-table-name voice-openai-connect-prod-HandoverTokens \
  --target-table-name voice-openai-connect-prod-HandoverTokens-restored \
  --restore-date-time 2024-01-01T12:00:00Z

# Update Terraform to use restored table
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v1
        with:
          role-to-assume: arn:aws:iam::ACCOUNT:role/github-actions
          aws-region: us-east-1

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2

      - name: Terraform Init
        run: terraform init
        working-directory: terraform

      - name: Terraform Plan
        run: terraform plan -out=tfplan
        working-directory: terraform

      - name: Terraform Apply
        run: terraform apply -auto-approve tfplan
        working-directory: terraform
```

## Cleanup

To destroy all infrastructure:

```bash
# WARNING: This will delete all resources!
terraform destroy

# Or target specific resources
terraform destroy -target=aws_ecs_service.gateway
```

## Support

For issues or questions:
1. Check CloudWatch Logs
2. Review CloudWatch Alarms
3. Check ECS service events
4. Review GitHub Issues

## License

See main project [LICENSE](../LICENSE) file.
