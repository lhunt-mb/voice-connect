# Quick Start Guide

Get up and running with Voice OpenAI Connect in 10 minutes.

## Prerequisites Checklist

- [ ] Python 3.12+ installed
- [ ] Docker and Docker Compose installed
- [ ] Twilio account with phone number
- [ ] OpenAI API key with Realtime API access
- [ ] HubSpot account with private app token
- [ ] AWS account (for DynamoDB and Lambda)
- [ ] Amazon Connect instance

## 5-Minute Local Setup

### 1. Install Dependencies (1 min)

```bash
pip install -e ".[dev]"
```

### 2. Configure Environment (2 min)

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
# Minimum required for local testing
PUBLIC_HOST=your-subdomain.ngrok.io
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+61xxxxxxxx
OPENAI_API_KEY=sk-proj-xxxxxx
CONNECT_PHONE_NUMBER=+61xxxxxxxx
CONNECT_INSTANCE_ID=xxxxxxxx
HUBSPOT_ACCESS_TOKEN=pat-xxxxxxxx

# For local dev
USE_LOCAL_DYNAMODB=true
DYNAMODB_ENDPOINT_URL=http://localhost:8001
```

### 3. Start Services (1 min)

```bash
docker-compose up -d
```

This starts:
- Gateway on `http://localhost:8000`
- DynamoDB Local on `http://localhost:8001`

### 4. Expose with ngrok (1 min)

```bash
ngrok http 8000
```

Copy your ngrok URL (e.g., `abc123.ngrok.io`) and update `.env`:
```bash
PUBLIC_HOST=abc123.ngrok.io
```

Restart gateway:
```bash
docker-compose restart gateway
```

### 5. Configure Twilio (1 min)

In Twilio Console:
1. Go to your phone number settings
2. Under "Voice & Fax", set:
   - **A CALL COMES IN**: Webhook
   - **URL**: `https://abc123.ngrok.io/twilio/voice`
   - **HTTP**: POST

## Test Your Setup

### 1. Check Health

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

### 2. Make a Test Call

Call your Twilio number. You should:
1. Hear "Please wait while we connect you"
2. Bot starts speaking
3. You can converse with the AI

### 3. Test Escalation

Say one of these phrases:
- "I need to speak with an agent"
- "Can I talk to a human?"
- "Connect me to a representative"

The system should:
1. Create HubSpot contact and ticket
2. Store token in DynamoDB
3. Call Amazon Connect with DTMF token

### 4. View Logs

```bash
docker-compose logs -f gateway
```

Look for JSON logs with correlation IDs.

## AWS Setup (Production)

### 1. Create DynamoDB Table (2 min)

```bash
./scripts/create_dynamodb_table.sh
```

Or manually:
```bash
aws dynamodb create-table \
  --table-name HandoverTokens \
  --attribute-definitions AttributeName=token,AttributeType=S \
  --key-schema AttributeName=token,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

aws dynamodb update-time-to-live \
  --table-name HandoverTokens \
  --time-to-live-specification "Enabled=true,AttributeName=expires_at"
```

### 2. Deploy Lambda (3 min)

```bash
cd aws/connect_lambda
zip lambda-package.zip handler.py

aws lambda create-function \
  --function-name ConnectTokenLookup \
  --runtime python3.12 \
  --role arn:aws:iam::ACCOUNT_ID:role/lambda-execution-role \
  --handler handler.lambda_handler \
  --zip-file fileb://lambda-package.zip \
  --environment "Variables={DYNAMODB_TABLE_NAME=HandoverTokens,AWS_REGION=ap-southeast-2}"
```

### 3. Configure Amazon Connect (5 min)

1. **Add Lambda to Connect**
   - Amazon Connect Console → Contact flows
   - Add Lambda function: `ConnectTokenLookup`

2. **Create Contact Flow**
   - Import flow or create manually
   - Key blocks:
     - Store customer input (DTMF) → `$.Attributes.token`
     - Invoke AWS Lambda → Pass `token` parameter
     - Check `$.External.success` attribute
     - Set contact attributes from Lambda response
     - Transfer to queue based on `route_to_queue`

3. **Assign Phone Number**
   - Update `.env` with Connect phone number
   - Ensure it routes to your contact flow

## HubSpot Setup (5 min)

### 1. Create Private App

1. HubSpot Settings → Integrations → Private Apps
2. Create app with scopes:
   - `crm.objects.contacts.read`
   - `crm.objects.contacts.write`
   - `tickets`
   - `crm.objects.notes.write`
3. Copy access token to `.env`

### 2. Verify Integration

After escalation, check:
- HubSpot Contact created with phone number
- Ticket created and associated with contact
- Note added to ticket with metadata

## Common Issues

### "OpenAI WebSocket failed to connect"

- Check API key is valid
- Verify internet connectivity
- Check OpenAI status page

### "Twilio webhook timeout"

- Ensure ngrok is running
- Check PUBLIC_HOST in `.env`
- Verify gateway is accessible: `curl https://abc123.ngrok.io/health`

### "DynamoDB throttling"

- Increase provisioned capacity or use on-demand
- Check AWS credentials are correct
- Verify table exists

### "HubSpot 401 error"

- Verify access token is correct
- Check token hasn't expired
- Ensure scopes are sufficient

## Next Steps

1. **Run Tests**
   ```bash
   pytest tests/ -v
   ```

2. **Review Logs**
   - Understand JSON log format
   - Note correlation IDs
   - Set up log aggregation (CloudWatch, ELK, etc.)

3. **Production Deployment**
   - Deploy to ECS/EKS/EC2
   - Set up ALB with WebSocket support
   - Use AWS Secrets Manager for credentials
   - Configure CloudWatch metrics

4. **Read Documentation**
   - [README.md](README.md) - Full documentation
   - [ARCHITECTURE.md](ARCHITECTURE.md) - System design
   - [CONTRIBUTING.md](CONTRIBUTING.md) - Development guide

## Support

- Issues: GitHub Issues
- Questions: Open discussion issue
- Documentation: [README.md](README.md)

---

**You're ready!** 🚀

Call your Twilio number and start conversing with your AI voice assistant.
