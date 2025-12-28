# Voice OpenAI Connect

Enterprise conversational AI gateway integrating Twilio, voice AI providers (OpenAI Realtime API or Amazon Nova 2 Sonic), and Amazon Connect for seamless voice-to-human escalation workflows.

## Architecture

This system implements Pattern A architecture for enterprise voice AI:

```
┌─────────────┐         ┌──────────────────┐         ┌────────────────┐
│   Twilio    │         │   AI Voice       │         │    OpenAI      │
│   PSTN      │◄───────►│   Gateway        │◄───────►│   Realtime     │
│   Call      │ WebSocket│   (FastAPI)     │ WebSocket│   or Nova 2   │
└─────────────┘         └──────────────────┘         └────────────────┘
                               │      │
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

## Features

- **Real-time Voice AI**: Bi-directional audio streaming between Twilio and your choice of voice provider (OpenAI Realtime API or Amazon Nova 2 Sonic)
- **Dual Provider Support**: Seamlessly switch between OpenAI Realtime and Amazon Nova 2 Sonic via configuration
- **Concurrent Sessions**: Async architecture supporting many simultaneous calls
- **Smart Escalation**: Keyword-based escalation to human agents in Amazon Connect
- **Token-based Handover**: Secure DTMF token system for context transfer
- **CRM Integration**: Automatic HubSpot contact and ticket creation
- **Production-Ready**: Fully typed Python 3.12, structured logging, comprehensive tests

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Twilio account with voice number
- Voice AI provider: **Either** OpenAI API access (Realtime API) **or** AWS Bedrock access (Amazon Nova 2 Sonic)
- AWS account (DynamoDB, Lambda, and optionally Bedrock for Nova 2)
- Amazon Connect instance
- HubSpot account with private app token

### Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd voice-openai-connect
   ```

2. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Start local services**
   ```bash
   docker-compose up
   ```

   This starts:
   - Gateway service on http://localhost:8000
   - DynamoDB Local on http://localhost:8001

5. **Expose with ngrok**
   ```bash
   ngrok http 8000
   ```

   Update `.env` with your ngrok URL:
   ```
   PUBLIC_HOST=your-subdomain.ngrok.io
   ```

6. **Configure Twilio webhook**

   In your Twilio console, set the voice webhook for your number to:
   ```
   https://your-subdomain.ngrok.io/twilio/voice
   ```

7. **Choose your voice provider**

   In your `.env` file, set:
   ```
   # For OpenAI Realtime
   VOICE_PROVIDER=openai
   OPENAI_API_KEY=sk-proj-xxxxx

   # OR for Amazon Nova 2 Sonic
   VOICE_PROVIDER=nova
   AWS_REGION=us-east-1
   ```

8. **Test a call**

   Call your Twilio number and speak with the AI assistant!

## Project Structure

```
voice-openai-connect/
├── shared/                    # Shared utilities
│   ├── config.py             # Pydantic settings
│   ├── logging.py            # Structured JSON logging
│   ├── types.py              # Type definitions
│   ├── aws_clients.py        # AWS client factories
│   └── retry.py              # Retry policies
├── services/
│   ├── orchestrator/         # Business logic & integrations
│   │   ├── voice_client_base.py     # Abstract voice client interface
│   │   ├── openai_realtime.py       # OpenAI WebSocket client
│   │   ├── nova_client.py           # Amazon Nova 2 Sonic client
│   │   ├── dynamo_repository.py     # DynamoDB operations
│   │   ├── hubspot_client.py        # HubSpot API client
│   │   ├── twilio_client.py         # Twilio API client
│   │   ├── token_generator.py       # Token generation
│   │   ├── escalation.py            # Escalation logic
│   │   └── orchestrator.py          # Main orchestration
│   └── gateway/              # FastAPI gateway service
│       ├── app.py            # FastAPI application
│       ├── session_manager.py       # Session state management
│       └── stream_handler.py        # WebSocket stream handler
├── aws/
│   └── connect_lambda/       # Amazon Connect Lambda
│       ├── handler.py        # Lambda function
│       ├── requirements.txt
│       └── Dockerfile
├── tests/
│   └── unit/                 # Unit tests
├── pyproject.toml            # Project config & dependencies
├── docker-compose.yml        # Local development stack
└── Dockerfile                # Gateway service container
```

## Configuration

All configuration via environment variables (see [.env.example](.env.example)):

### Core Settings

| Variable | Description | Required |
|----------|-------------|----------|
| `PUBLIC_HOST` | Public hostname for webhooks | Yes |
| `LOG_LEVEL` | Logging level (INFO, DEBUG) | No |
| `VOICE_PROVIDER` | Voice provider: `openai` or `nova` | Yes |

### Twilio

| Variable | Description | Required |
|----------|-------------|----------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Yes |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Yes |
| `TWILIO_PHONE_NUMBER` | Twilio phone number | Yes |

### Voice Provider Configuration

#### OpenAI Realtime (when `VOICE_PROVIDER=openai`)

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `OPENAI_REALTIME_MODEL` | Model (default: gpt-4o-realtime-preview-2024-12-17) | No |
| `OPENAI_VOICE` | Voice (alloy, echo, fable, onyx, nova, shimmer) | No |

#### Amazon Nova 2 Sonic (when `VOICE_PROVIDER=nova`)

| Variable | Description | Required |
|----------|-------------|----------|
| `AWS_REGION` | AWS region (us-east-1, eu-north-1, ap-northeast-1) | Yes |
| `AWS_ACCESS_KEY_ID` | AWS access key | Yes* |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Yes* |

*Not required if using IAM roles. Nova 2 Sonic requires Bedrock permissions (`bedrock:InvokeModelWithResponseStream`).

### AWS

| Variable | Description | Required |
|----------|-------------|----------|
| `AWS_REGION` | AWS region | Yes |
| `AWS_ACCESS_KEY_ID` | AWS access key | Yes* |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Yes* |
| `DYNAMODB_TABLE_NAME` | DynamoDB table name | Yes |

*Not required if using IAM roles (EC2, ECS, Lambda). AWS credentials are always required for DynamoDB.

### Amazon Connect

| Variable | Description | Required |
|----------|-------------|----------|
| `CONNECT_PHONE_NUMBER` | Connect phone number | Yes |
| `CONNECT_INSTANCE_ID` | Connect instance ID | Yes |

### HubSpot

| Variable | Description | Required |
|----------|-------------|----------|
| `HUBSPOT_ACCESS_TOKEN` | HubSpot private app token | Yes |

## Amazon Connect Setup

### 1. Create DynamoDB Table

```bash
aws dynamodb create-table \
  --table-name HandoverTokens \
  --attribute-definitions AttributeName=token,AttributeType=S \
  --key-schema AttributeName=token,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --time-to-live-specification "Enabled=true,AttributeName=expires_at"
```

### 2. Deploy Lambda Function

```bash
cd aws/connect_lambda
docker build -t connect-lambda .
# Tag and push to ECR, then create Lambda function
```

Environment variables for Lambda:
- `DYNAMODB_TABLE_NAME=HandoverTokens`
- `AWS_REGION=ap-southeast-2`

### 3. Configure Contact Flow

Create a contact flow in Amazon Connect with these blocks:

```
1. Store customer input
   - Type: DTMF
   - Prompt: "Please enter your reference number followed by the pound key"
   - Timeout: 10 seconds
   - Store as: $.Attributes.token

2. Invoke AWS Lambda function
   - Function: ConnectTokenLookup
   - Timeout: 8 seconds
   - Parameters:
     * token: $.Attributes.token

3. Check contact attributes
   - Attribute: $.External.success
   - Condition: Equals "True"
     - Branch: Set contact attributes (all returned attributes)
     - Then: Transfer to queue (escalation)
   - Condition: Not equals "True"
     - Branch: Transfer to queue (fallback)

4. Transfer to queue
   - Queue: Based on route_to_queue attribute
   - Screen pop: Use hubspot_ticket_id for agent display
```

### Lambda Return Format

The Lambda function returns these attributes for Connect:

```json
{
  "success": true,
  "conversation_id": "uuid",
  "caller_phone": "+61...",
  "hubspot_contact_id": "...",
  "hubspot_ticket_id": "...",
  "summary": "Conversation summary...",
  "intent": "support",
  "priority": "high",
  "escalation_reason": "user_request",
  "route_to_queue": "escalation"
}
```

## Call Flow Sequence

```
1. Customer calls Twilio number
   └─> Twilio webhook: POST /twilio/voice
       └─> Returns TwiML with <Stream> directive

2. Twilio establishes WebSocket to /twilio/stream
   └─> Gateway creates session
   └─> Gateway connects to voice provider (OpenAI Realtime or Nova 2 Sonic)
   └─> Bi-directional audio streaming begins

3. Customer converses with AI
   └─> Audio: Twilio ←→ Gateway ←→ Voice Provider
   └─> Transcripts checked for escalation keywords

4. Escalation triggered (e.g., "I need an agent")
   └─> Generate 10-digit token
   └─> Create/update HubSpot contact
   └─> Create HubSpot ticket with summary
   └─> Store token + metadata in DynamoDB (TTL 10 min)
   └─> Initiate call to Connect with DTMF token
   └─> End bot session

5. Connect receives call with DTMF token
   └─> Contact flow captures token
   └─> Lambda validates token
   └─> Lambda fetches handover payload from DynamoDB
   └─> Set contact attributes
   └─> Route to appropriate queue
   └─> Agent sees screen pop with context
```

## Development

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit -m unit

# With coverage
pytest --cov --cov-report=html
```

### Code Quality

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type checking
pyright
```

### Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

## Deployment

### Gateway Service (Docker)

```bash
docker build -t voice-gateway .
docker run -p 8000:8000 --env-file .env voice-gateway
```

### Production Considerations

1. **Scaling**: Use container orchestration (ECS, Kubernetes) for horizontal scaling
2. **Load Balancing**: Place behind ALB with WebSocket support
3. **TLS**: Terminate TLS at load balancer or use reverse proxy
4. **Secrets**: Use AWS Secrets Manager or Parameter Store
5. **Monitoring**: CloudWatch metrics, logs, and traces
6. **DynamoDB**: Configure autoscaling or use on-demand billing

## Monitoring & Logging

All logs are structured JSON with correlation IDs:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "message": "Escalation triggered",
  "call_sid": "CA123...",
  "stream_sid": "ST456...",
  "conversation_id": "uuid",
  "handover_id": "1234567890"
}
```

Key metrics to monitor:
- Active sessions count
- Escalation rate
- Average session duration
- Voice provider connection failures (OpenAI or Nova 2)
- DynamoDB throttling
- Lambda invocation errors

## Troubleshooting

### Twilio WebSocket Disconnects

- Check voice provider connection health (OpenAI or Nova 2)
- Verify keepalive/silence handling
- Review correlation IDs in logs

### Escalation Failures

- Verify DynamoDB table exists and has TTL enabled
- Check HubSpot API token permissions
- Confirm Connect phone number is correct
- Review Lambda CloudWatch logs

### Audio Quality Issues

- Twilio sends mulaw 8kHz
  - OpenAI Realtime expects PCM16 (conversion may be needed)
  - Nova 2 Sonic natively supports mulaw 8kHz (ideal for telephony)
- Check network latency between services

## Security Considerations

- API keys and tokens stored in environment/secrets manager
- No PII in logs (phone numbers OK, no full transcripts)
- DynamoDB TTL ensures token expiry
- Lambda validates token format before lookup
- HubSpot API uses private app tokens with minimal scopes

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [repository-url]/issues
- Documentation: [docs-url]
