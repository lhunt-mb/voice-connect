# Deployment Guide - Voice OpenAI Connect

This guide walks you through deploying the Voice OpenAI Connect infrastructure to AWS using Terraform.

## Prerequisites Checklist

### AWS Setup
- [ ] AWS Account with appropriate permissions
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Permissions to create: VPC, ECS, Lambda, DynamoDB, ALB, IAM, KMS, Secrets Manager, ECR
- [ ] S3 bucket for Terraform state (recommended)
- [ ] DynamoDB table for state locking (recommended)

### Tools
- [ ] Terraform >= 1.0.0 installed
- [ ] Docker installed and running
- [ ] Git installed
- [ ] `jq` installed (optional, for JSON parsing)

### External Services
- [ ] Twilio account with:
  - Account SID
  - Auth Token
  - Phone number with voice capabilities
- [ ] Amazon Connect instance configured
- [ ] OpenAI API key (if using OpenAI provider) OR Bedrock access (if using Nova provider)
- [ ] HubSpot account with private app token (optional)

## Step-by-Step Deployment

### Step 1: Clone and Configure

```bash
# Clone the repository
git clone <repository-url>
cd voice-openai-connect/terraform

# Review the architecture
cat README.md
```

### Step 2: Configure Terraform Backend

Create `backend.hcl` for remote state storage:

```hcl
bucket         = "my-terraform-state-bucket"
key            = "voice-openai-connect/terraform.tfstate"
region         = "ap-southeast-2"
dynamodb_table = "terraform-state-locking"
encrypt        = true
```

**Create the backend resources first:**

```bash
# Create S3 bucket for state
aws s3api create-bucket \
  --bucket my-terraform-state-bucket \
  --region ap-southeast-2 \
  --create-bucket-configuration LocationConstraint=ap-southeast-2

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket my-terraform-state-bucket \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket my-terraform-state-bucket \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Create DynamoDB table for locking
aws dynamodb create-table \
  --table-name terraform-state-locking \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-southeast-2
```

### Step 3: Configure Variables

```bash
# Copy example file
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

**Required Variables:**

```hcl
# AWS Configuration
aws_region  = "ap-southeast-2"
environment = "dev"  # or "test", "prod"

# Networking
vpc_cidr            = "10.0.0.0/16"
availability_zones  = ["ap-southeast-2a", "ap-southeast-2b"]

# Twilio Credentials
twilio_account_sid   = "ACxxxxxxxxxxxxxxxxxxxx"
twilio_auth_token    = "your_auth_token_here"
twilio_phone_number  = "+15551234567"

# Voice Provider
voice_provider = "nova"  # or "openai"

# If using OpenAI:
openai_api_key = "sk-..."

# If using Nova:
nova_region            = "us-east-1"
enable_bedrock_access  = true

# Amazon Connect
connect_phone_number  = "+15551234567"
connect_instance_id   = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

# Optional but recommended
alarm_email       = "alerts@example.com"
certificate_arn   = "arn:aws:acm:ap-southeast-2:..." # For HTTPS
domain_name       = "voice.example.com"              # Custom domain
```

**IMPORTANT**: Add `terraform.tfvars` to `.gitignore` to avoid committing secrets!

### Step 4: Initialize Terraform

```bash
# Initialize with backend config
terraform init -backend-config=backend.hcl

# OR without backend (local state)
terraform init -backend=false
```

Expected output:
```
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.0"...
- Installing hashicorp/aws v5.100.0...

Terraform has been successfully initialized!
```

### Step 5: Build and Push Docker Images

Before deploying, you need to build and push your Docker images to ECR.

```bash
# First, create ECR repositories
terraform apply -target=aws_ecr_repository.gateway -target=aws_ecr_repository.lambda

# Set variables
export AWS_REGION=ap-southeast-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export GATEWAY_ECR="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/voice-openai-connect/gateway"
export LAMBDA_ECR="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/voice-openai-connect/connect-lambda"

# Authenticate Docker to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Build and push Gateway image
cd ..
docker build -t ${GATEWAY_ECR}:latest -f Dockerfile .
docker push ${GATEWAY_ECR}:latest

# Build and push Lambda image
cd aws/connect_lambda
docker build -t ${LAMBDA_ECR}:latest -f Dockerfile .
docker push ${LAMBDA_ECR}:latest

cd ../../terraform
```

### Step 6: Review Terraform Plan

```bash
# Generate execution plan
terraform plan -out=tfplan

# Review the plan carefully
# Look for:
# - Resources to be created
# - Any unexpected changes
# - Security configurations
```

Expected resources:
- VPC with public/private subnets
- Application Load Balancer
- ECS Cluster and Service
- Lambda Function
- DynamoDB Table
- IAM Roles and Policies
- Security Groups
- VPC Endpoints
- CloudWatch Log Groups
- KMS Keys
- Secrets Manager Secret

### Step 7: Apply Infrastructure

```bash
# Apply the plan
terraform apply tfplan

# Review and confirm
# Type 'yes' when prompted
```

Deployment time: ~10-15 minutes

### Step 8: Verify Deployment

```bash
# Get outputs
terraform output

# Important outputs:
# - gateway_endpoint: ALB DNS name
# - twilio_webhook_url: Configure in Twilio
# - twilio_stream_url: WebSocket endpoint
# - lambda_function_arn: Use in Amazon Connect
```

**Verify ECS Service:**

```bash
# Check ECS service status
aws ecs describe-services \
  --cluster voice-openai-connect-dev-cluster \
  --services voice-openai-connect-dev-gateway \
  --region ap-southeast-2

# Check running tasks
aws ecs list-tasks \
  --cluster voice-openai-connect-dev-cluster \
  --service-name voice-openai-connect-dev-gateway \
  --region ap-southeast-2
```

**Verify ALB Health:**

```bash
# Check target health
TARGET_GROUP_ARN=$(terraform output -raw alb_target_group_arn)
aws elbv2 describe-target-health \
  --target-group-arn ${TARGET_GROUP_ARN} \
  --region ap-southeast-2
```

### Step 9: Configure External Services

#### Configure Twilio

1. Go to [Twilio Console](https://console.twilio.com/)
2. Navigate to Phone Numbers → Manage Numbers
3. Select your phone number
4. Under Voice & Fax:
   - **A Call Comes In**: Webhook
   - **URL**: Copy from `terraform output twilio_webhook_url`
   - **Method**: POST
5. Save configuration

#### Configure Amazon Connect

1. Go to [Amazon Connect Console](https://console.aws.amazon.com/connect/)
2. Select your instance
3. Navigate to Contact Flows → AWS Lambda
4. Add Lambda function:
   - **Function ARN**: Copy from `terraform output lambda_function_arn`
5. Create/edit contact flow:
   - Add "Get customer input" block (DTMF, 10 digits)
   - Add "Invoke AWS Lambda function" block
   - Select your Lambda function
   - Use Lambda response attributes for screen pop
   - Route to appropriate queue

### Step 10: Test the Deployment

#### Test Health Endpoint

```bash
ALB_DNS=$(terraform output -raw alb_dns_name)
curl http://${ALB_DNS}/health
# Expected: {"status": "healthy"}
```

#### Test End-to-End Call Flow

1. Call your Twilio phone number
2. Verify AI voice response
3. Say escalation keyword (e.g., "I need an agent")
4. Verify call transfer to Amazon Connect
5. Verify agent receives context information

#### Monitor Logs

```bash
# Gateway service logs
aws logs tail /ecs/voice-openai-connect-dev-gateway --follow

# Lambda logs
aws logs tail /aws/lambda/voice-openai-connect-dev-connect-lookup --follow
```

## Post-Deployment Configuration

### Set Up Custom Domain (Optional)

If you provided `certificate_arn` and `domain_name`:

```bash
# Get ALB DNS from outputs
ALB_DNS=$(terraform output -raw alb_dns_name)
ALB_ZONE_ID=$(terraform output -raw alb_zone_id)

# Create Route 53 record
aws route53 change-resource-record-sets \
  --hosted-zone-id <your-hosted-zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "voice.example.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "'${ALB_ZONE_ID}'",
          "DNSName": "'${ALB_DNS}'",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'
```

### Configure CloudWatch Alarms

If you provided `alarm_email`:

1. Check your email for SNS subscription confirmation
2. Click the confirmation link
3. Alarms will now send notifications to your email

### Enable Additional Monitoring

```bash
# View CloudWatch Dashboard
DASHBOARD_NAME=$(terraform output -json | jq -r '.cloudwatch_dashboard_url.value')
open ${DASHBOARD_NAME}
```

## Environment-Specific Configurations

### Development Environment

```hcl
environment                = "dev"
gateway_desired_count      = 1
gateway_min_capacity       = 1
gateway_max_capacity       = 3
enable_container_insights  = false  # Save costs
```

### Production Environment

```hcl
environment                = "prod"
gateway_desired_count      = 4
gateway_min_capacity       = 2
gateway_max_capacity       = 20
enable_container_insights  = true
certificate_arn            = "arn:aws:acm:..."  # HTTPS required
domain_name                = "voice.example.com"
alarm_email                = "oncall@example.com"
```

## Updating the Infrastructure

### Update Application Code

```bash
# Build new image with version tag
docker build -t ${GATEWAY_ECR}:v1.0.1 .
docker push ${GATEWAY_ECR}:v1.0.1

# Update Terraform variable
echo 'gateway_image_tag = "v1.0.1"' >> terraform.tfvars

# Apply changes
terraform plan -out=tfplan
terraform apply tfplan
```

### Update Infrastructure

```bash
# Make changes to .tf files
# Validate changes
terraform validate

# Review plan
terraform plan

# Apply changes
terraform apply
```

### Rolling Back

```bash
# Revert to previous state version
terraform state pull > backup.tfstate

# Or revert code changes and reapply
git revert <commit-hash>
terraform apply
```

## Troubleshooting

### ECS Tasks Not Starting

```bash
# Check service events
aws ecs describe-services \
  --cluster voice-openai-connect-dev-cluster \
  --services voice-openai-connect-dev-gateway

# Check task logs
aws logs tail /ecs/voice-openai-connect-dev-gateway --follow

# Common issues:
# 1. Image not found in ECR → Push image first
# 2. Secrets not accessible → Check IAM permissions
# 3. Health check failing → Check /health endpoint
```

### Terraform State Locked

```bash
# List locks
aws dynamodb get-item \
  --table-name terraform-state-locking \
  --key '{"LockID":{"S":"my-terraform-state-bucket/voice-openai-connect/terraform.tfstate-md5"}}'

# Force unlock (use with caution!)
terraform force-unlock <lock-id>
```

### Certificate Validation Pending

If using ACM certificate:

```bash
# Check certificate status
aws acm describe-certificate \
  --certificate-arn <certificate-arn>

# If pending validation, add DNS records
# Follow instructions in ACM console
```

## Security Best Practices

1. **Never commit `terraform.tfvars`** with real credentials
2. **Use backend encryption** for state files
3. **Enable MFA** for AWS account
4. **Rotate secrets** regularly in Secrets Manager
5. **Review CloudWatch alarms** weekly
6. **Run security scans** before production deployment
7. **Enable AWS GuardDuty** for threat detection

## Cleanup / Destruction

⚠️ **WARNING**: This will delete all infrastructure and data!

```bash
# Review what will be destroyed
terraform plan -destroy

# Destroy infrastructure
terraform destroy

# Confirm by typing 'yes'

# Optionally, delete ECR images first
aws ecr batch-delete-image \
  --repository-name voice-openai-connect/gateway \
  --image-ids imageTag=latest

aws ecr batch-delete-image \
  --repository-name voice-openai-connect/connect-lambda \
  --image-ids imageTag=latest
```

## Cost Estimation

Estimated monthly costs for ap-southeast-2 (Sydney):

| Component | Development | Production |
|-----------|-------------|------------|
| ECS Fargate | $33 | $132 |
| ALB | $23 | $28 |
| NAT Gateway | $38 | $76 |
| DynamoDB | $5 | $22 |
| Lambda | $5 | $22 |
| VPC Endpoints | $16 | $16 |
| CloudWatch | $10 | $33 |
| **Total** | **~$130/mo** | **~$330/mo** |

*Note: ap-southeast-2 pricing is approximately 10% higher than us-east-1. Plus: Twilio costs, OpenAI/Bedrock API costs, HubSpot costs, data transfer*

## Support

For issues:
1. Check [README.md](terraform/README.md)
2. Review [SECURITY.md](terraform/SECURITY.md)
3. Check CloudWatch Logs
4. Review Terraform state: `terraform show`
5. Contact DevOps team

## Next Steps

After successful deployment:

1. ✅ Configure monitoring and alerting
2. ✅ Set up CI/CD pipeline
3. ✅ Configure backup and disaster recovery
4. ✅ Perform security audit
5. ✅ Load testing
6. ✅ Documentation for operators
7. ✅ Runbooks for common operations

## Appendix: Useful Commands

```bash
# View all outputs
terraform output

# View specific output
terraform output alb_dns_name

# List all resources
terraform state list

# Show resource details
terraform show

# Import existing resource
terraform import aws_s3_bucket.example my-bucket

# Refresh state
terraform refresh

# Format code
terraform fmt -recursive

# Validate configuration
terraform validate

# View Terraform version
terraform version
```
