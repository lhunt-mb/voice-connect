# Getting Started with Voice OpenAI Connect

Complete guide to get your enterprise voice AI gateway up and running.

## What You've Got

A production-ready Python 3.12 mono-repo with:
- ✅ **2,227 lines** of fully-typed Python code
- ✅ **5 services**: Gateway, Orchestrator, OpenAI client, DynamoDB, HubSpot client
- ✅ **1 Lambda function**: Amazon Connect token validation
- ✅ **Comprehensive tests**: Unit tests with pytest
- ✅ **Full documentation**: 1,500+ lines across 8 documents
- ✅ **Production tooling**: Docker, CI/CD, pre-commit hooks
- ✅ **Zero secrets**: All configuration via environment variables

## Installation (2 minutes)

### 1. Install Python Dependencies

```bash
# Install the package in editable mode with dev dependencies
pip install -e ".[dev]"
```

This installs:
- **Production**: FastAPI, uvicorn, websockets, httpx, pydantic, boto3, etc.
- **Development**: ruff, pyright, pytest, pytest-asyncio, moto, pre-commit

### 2. Install Pre-commit Hooks (Optional)

```bash
pre-commit install
```

This runs Ruff (format + lint), Pyright, and pytest automatically on every commit.

## Configuration (5 minutes)

### 1. Copy Environment Template

```bash
cp .env.example .env
```

### 2. Edit .env with Your Credentials

**Minimum Required for Local Testing:**

```bash
# Server
PUBLIC_HOST=your-subdomain.ngrok.io  # Will get this in step 3

# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+61XXXXXXXXX

# OpenAI
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx

# Amazon Connect
CONNECT_PHONE_NUMBER=+61XXXXXXXXX
CONNECT_INSTANCE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# HubSpot
HUBSPOT_ACCESS_TOKEN=pat-xx-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Local development
USE_LOCAL_DYNAMODB=true
DYNAMODB_ENDPOINT_URL=http://localhost:8001
```

**Where to get these:**
- **Twilio**: Console → Account → Account SID, Auth Token, Phone Numbers
- **OpenAI**: Platform → API keys (need Realtime API access)
- **HubSpot**: Settings → Integrations → Private Apps → Create app
- **AWS/Connect**: AWS Console → Amazon Connect → Instance

## Running Locally (3 minutes)

### Option 1: Docker Compose (Recommended)

```bash
# Start gateway + DynamoDB Local
docker-compose up -d

# View logs
docker-compose logs -f gateway

# Stop services
docker-compose down
```

Gateway runs on: `http://localhost:8000`
DynamoDB Local on: `http://localhost:8001`

### Option 2: Direct Python

```bash
# Terminal 1: Start DynamoDB Local (requires Docker)
docker run -p 8001:8000 amazon/dynamodb-local

# Terminal 2: Start gateway
python -m uvicorn services.gateway.app:app --host 0.0.0.0 --port 8000
```

### 3. Expose with ngrok

```bash
# Install ngrok if needed: brew install ngrok
ngrok http 8000
```

Copy your ngrok URL (e.g., `abc123.ngrok-free.app`) and:
1. Update `.env`: `PUBLIC_HOST=abc123.ngrok-free.app`
2. Restart gateway: `docker-compose restart gateway`

### 4. Configure Twilio Webhook

1. Go to Twilio Console → Phone Numbers → Your number
2. Under "Voice & Fax":
   - **A CALL COMES IN**: Webhook
   - **URL**: `https://abc123.ngrok-free.app/twilio/voice`
   - **HTTP**: POST

## Testing (5 minutes)

### 1. Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

### 2. Make a Test Call

Call your Twilio number. You should:
1. Hear: "Please wait while we connect you"
2. Bot starts speaking
3. Have a conversation

### 3. Trigger Escalation

Say one of these:
- "I need to speak with an agent"
- "Can I talk to a human?"
- "Connect me to a representative"

Expected behavior:
1. Bot acknowledges your request
2. System creates HubSpot contact + ticket
3. Stores token in DynamoDB
4. Calls Amazon Connect with DTMF token
5. Call ends

### 4. Check Logs

```bash
docker-compose logs -f gateway
```

Look for JSON logs like:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "message": "Escalation triggered",
  "call_sid": "CAxxxx",
  "stream_sid": "STxxxx",
  "conversation_id": "uuid",
  "handover_id": "1234567890"
}
```

## Development Workflow

### Code Quality

```bash
# Format code
make format

# Lint
make lint

# Type check
make typecheck

# All checks
make format lint typecheck
```

### Testing

```bash
# Run all tests
make test

# Unit tests only
make test-unit

# With coverage
make test-cov
```

### Git Workflow

```bash
# Pre-commit hooks run automatically on commit
git add .
git commit -m "feat: add new feature"

# Push to remote
git push origin main
```

## AWS Setup (Production)

### 1. Create DynamoDB Table

```bash
./scripts/create_dynamodb_table.sh
```

Or manually:
```bash
aws dynamodb create-table \
  --table-name HandoverTokens \
  --attribute-definitions AttributeName=token,AttributeType=S \
  --key-schema AttributeName=token,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-southeast-2

aws dynamodb update-time-to-live \
  --table-name HandoverTokens \
  --time-to-live-specification "Enabled=true,AttributeName=expires_at" \
  --region ap-southeast-2
```

### 2. Deploy Lambda

```bash
cd aws/connect_lambda
zip lambda-package.zip handler.py

aws lambda create-function \
  --function-name ConnectTokenLookup \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role \
  --handler handler.lambda_handler \
  --zip-file fileb://lambda-package.zip \
  --environment "Variables={DYNAMODB_TABLE_NAME=HandoverTokens,AWS_REGION=ap-southeast-2}" \
  --region ap-southeast-2
```

### 3. Configure Amazon Connect

See detailed instructions in [README.md → Amazon Connect Setup](README.md#amazon-connect-setup)

Key steps:
1. Add Lambda to Connect instance
2. Create contact flow with DTMF capture
3. Invoke Lambda with token parameter
4. Set contact attributes from response
5. Route to queue based on attributes

## Project Structure

```
services/
├── gateway/              # FastAPI service
│   ├── app.py           # HTTP + WebSocket endpoints
│   ├── session_manager.py
│   └── stream_handler.py
└── orchestrator/         # Business logic
    ├── openai_realtime.py
    ├── orchestrator.py
    └── [other integrations]

shared/                   # Utilities
├── config.py            # Settings
├── logging.py           # JSON logs
└── types.py             # Models

aws/connect_lambda/      # Lambda function
tests/unit/              # Unit tests
```

## Next Steps

### 1. Read Documentation

- **[README.md](README.md)** - Complete guide
- **[QUICKSTART.md](QUICKSTART.md)** - Fast setup
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design

### 2. Customize

- Modify escalation keywords in [escalation.py](services/orchestrator/escalation.py)
- Adjust OpenAI instructions in [openai_realtime.py](services/orchestrator/openai_realtime.py)
- Configure HubSpot ticket priority logic

### 3. Deploy to Production

- Review [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
- Set up AWS infrastructure (ECS, ALB, CloudWatch)
- Configure monitoring and alerts
- Run load tests

### 4. Monitor

- CloudWatch Logs for gateway and Lambda
- DynamoDB metrics (throttles, capacity)
- Custom metrics (escalation rate, session duration)

## Common Commands

```bash
# Development
make dev-install        # Install dependencies + pre-commit
make format            # Format code
make lint              # Lint code
make typecheck         # Type check
make test              # Run tests
make test-cov          # Tests with coverage

# Docker
make docker-build      # Build image
make docker-up         # Start services
make docker-down       # Stop services
make docker-logs       # View logs

# Cleanup
make clean             # Remove build artifacts
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'pydantic'"

```bash
pip install -e ".[dev]"
```

### "Connection refused" when calling service

Check services are running:
```bash
docker-compose ps
# or
curl http://localhost:8000/health
```

### "OpenAI WebSocket failed to connect"

- Verify `OPENAI_API_KEY` is correct
- Check OpenAI status: https://status.openai.com
- Ensure Realtime API access enabled

### "Twilio webhook timeout"

- Ensure ngrok is running: `ngrok http 8000`
- Update `PUBLIC_HOST` in `.env`
- Restart gateway: `docker-compose restart gateway`

### "DynamoDB ResourceNotFoundException"

For local dev:
```bash
docker-compose up dynamodb-local
```

For production:
```bash
./scripts/create_dynamodb_table.sh
```

## Getting Help

1. **Documentation**: Check [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Issues**: Open a GitHub issue
3. **Logs**: Always check logs first: `docker-compose logs -f gateway`

## Key Files Reference

| File | Purpose |
|------|---------|
| [services/gateway/app.py](services/gateway/app.py) | FastAPI application |
| [services/orchestrator/orchestrator.py](services/orchestrator/orchestrator.py) | Escalation workflow |
| [aws/connect_lambda/handler.py](aws/connect_lambda/handler.py) | Lambda function |
| [shared/config.py](shared/config.py) | Configuration |
| [.env.example](.env.example) | Config template |

## Architecture Diagram

```
┌─────────────┐         ┌──────────────────┐         ┌────────────────┐
│   Twilio    │         │   AI Voice       │         │    OpenAI      │
│   PSTN      │◄───────►│   Gateway        │◄───────►│   Realtime     │
│   Call      │ WebSocket│   (FastAPI)     │ WebSocket│     API       │
└─────────────┘         └──────────────────┘         └────────────────┘
                               │      │
                        ┌──────┘      └──────┐
                        ▼                     ▼
                   ┌─────────┐          ┌──────────┐
                   │DynamoDB │          │ HubSpot  │
                   │ Tokens  │          │   CRM    │
                   └─────────┘          └──────────┘
                        │
                        │ DTMF Token
                        ▼
                   ┌─────────────────┐
                   │ Amazon Connect  │
                   │  Contact Flow   │
                   │    + Lambda     │
                   └─────────────────┘
```

---

**You're all set!** 🚀

Call your Twilio number and start building your enterprise voice AI system.
