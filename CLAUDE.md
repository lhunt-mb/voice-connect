# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Enterprise conversational AI gateway integrating Twilio voice calls with AI voice providers (OpenAI Realtime API or Amazon Nova 2 Sonic) and Amazon Connect for human escalation. Python 3.12 monorepo with async FastAPI gateway, fully typed codebase, and production-ready infrastructure.

## Common Commands

### Development

```bash
# Install dependencies with dev tools
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Code quality checks
make format              # Format with ruff
make lint               # Lint with ruff
make typecheck          # Type check with pyright

# Testing
make test               # Run all tests
make test-unit          # Run unit tests only
make test-cov           # Tests with coverage report
pytest tests/unit/test_prompts.py -m "not deepeval"  # Prompt tests (no LLM)
pytest tests/unit/test_prompts.py -m deepeval        # Prompt quality tests (requires OPENAI_API_KEY)

# Run single test file
pytest tests/unit/test_token_generator.py -v
```

### Local Development

```bash
# Start services (gateway + DynamoDB Local)
docker-compose up -d

# View logs
docker-compose logs -f gateway

# Stop services
docker-compose down

# Direct Python run (alternative to Docker)
python -m uvicorn services.gateway.app:app --host 0.0.0.0 --port 8000
```

### Terraform Deployment

```bash
cd terraform/

# Initialize (first time)
terraform init

# Plan changes
terraform plan

# Apply infrastructure
terraform apply

# Check formatting
terraform fmt -recursive
```

## High-Level Architecture

### Pipecat Framework (Default)

The system uses **Pipecat** (https://pipecat.ai) for voice AI pipeline orchestration. Pipecat provides:

- Unified pipeline architecture for audio streaming
- Native support for OpenAI Realtime and Nova 2 Sonic
- Built-in Twilio WebSocket serialization
- Modular, testable frame processors

**Architecture with Pipecat:**
```
Twilio WebSocket → FastAPIWebsocketTransport → Voice AI Service → EscalationProcessor → Transport Output
                   (TwilioFrameSerializer)     (OpenAI/Nova)      (keyword detection)
```

Switch between implementations via `USE_PIPECAT` environment variable (default: `true`).

### Voice Provider Abstraction

**Pipecat Mode (USE_PIPECAT=true):**
- Voice providers configured via Pipecat's service adapters
- Escalation handled by `EscalationProcessor` frame processor
- Cleaner, more testable code

**Legacy Mode (USE_PIPECAT=false):**
Uses the `VoiceClientBase` abstract class:

- **OpenAI Realtime** (`openai_realtime.py`): WebSocket-based, requires PCM16 audio conversion
- **Nova 2 Sonic** (`nova_sonic.py`): AWS Bedrock bidirectional streaming, native G.711 μ-law support

Switch providers via `VOICE_PROVIDER` environment variable (`openai` or `nova`).

### Session Management & Concurrency

Each call creates an isolated session in `SessionManager` (by `stream_sid`). All I/O is **async** using `asyncio` to support multiple concurrent calls.

- **Pipecat mode**: Pipeline runner manages the stream lifecycle
- **Legacy mode**: `StreamHandler` manages bidirectional audio

**Important**: The gateway is stateless except for in-memory sessions. For horizontal scaling, implement sticky sessions at load balancer or use Redis for distributed state.

### Escalation Workflow

Triggered by keyword detection in user transcripts (see `escalation.py`):

1. Generate 10-digit DTMF token
2. Create/update HubSpot contact + ticket with conversation summary
3. Store token + conversation metadata in DynamoDB (TTL 10 minutes)
4. Call Amazon Connect phone number with DTMF token
5. Lambda function (`aws/connect_lambda/handler.py`) validates token and returns attributes
6. Connect routes to queue based on attributes

**Critical**: The Lambda must be invoked from Connect contact flow with the token as a parameter. It returns structured attributes for routing and screen pop.

### Multi-Region Support (Nova 2 Only)

When using Nova 2 Sonic, the system supports **cross-region deployment**:

- `AWS_REGION`: Where DynamoDB and Lambda run (any region for compliance/latency)
- `NOVA_REGION`: Where Nova 2 Sonic model runs (must be `us-east-1`, `eu-north-1`, or `ap-northeast-1`)

Example: Deploy DynamoDB in `ap-southeast-2` for data residency, use Nova 2 from `ap-northeast-1` for lower latency.

### AI Prompt Management

Prompts are **abstracted and testable** via `AssistantPrompt` dataclass in `prompts.py`:

- Predefined prompts: `DEFAULT_ASSISTANT_PROMPT`, `TECHNICAL_SUPPORT_PROMPT`, `SALES_ASSISTANT_PROMPT`
- Use `get_prompt("sales")` to retrieve by name
- Custom prompts: Create new `AssistantPrompt` instances
- Testing: Unit tests validate structure, DeepEval tests evaluate quality (requires `OPENAI_API_KEY`)

**When modifying prompts**: Always run `pytest tests/unit/test_prompts.py -m "not deepeval"` to verify structure before committing.

## Code Organization

### Module Structure

```
shared/                          # Cross-service utilities (no external dependencies)
├── config.py                   # Pydantic Settings - single source of configuration
├── logging.py                  # Structured JSON logging with correlation IDs
├── types.py                    # Shared type definitions
├── aws_clients.py              # AWS client factories with retry policies
└── retry.py                    # Tenacity retry decorators

services/pipecat/                # Pipecat voice AI pipeline (DEFAULT)
├── __init__.py                 # Public exports
├── pipeline_factory.py         # Creates configured voice pipelines
├── escalation_processor.py     # Frame processor for escalation detection
└── README.md                   # Pipecat integration documentation

services/orchestrator/           # Business logic layer
├── voice_client_base.py        # Abstract interface for voice providers (legacy)
├── openai_realtime.py          # OpenAI Realtime WebSocket client (legacy)
├── nova_sonic.py               # Amazon Nova 2 Bedrock streaming client (legacy)
├── prompts.py                  # AI prompt configurations (testable)
├── escalation.py               # Escalation keyword detection and triggers
├── orchestrator.py             # Main escalation workflow coordinator
├── dynamo_repository.py        # DynamoDB operations with async support
├── hubspot_client.py           # HubSpot API client with retry logic
├── twilio_client.py            # Twilio API calls
└── token_generator.py          # Secure random token generation

services/gateway/                # FastAPI HTTP/WebSocket gateway
├── app.py                      # FastAPI app with Twilio webhooks (legacy mode)
├── app_pipecat.py              # FastAPI app using Pipecat (default)
├── session_manager.py          # Per-call session state management
└── stream_handler.py           # Bidirectional audio streaming (legacy)

aws/connect_lambda/              # Amazon Connect integration
└── handler.py                  # Lambda: validates token, returns attributes

tests/unit/                      # Unit tests (pytest + pytest-asyncio)
├── test_prompts.py             # Prompt tests (includes DeepEval marker)
└── test_pipecat_pipeline.py    # Pipecat pipeline tests
```

### Key Design Patterns

1. **Settings Pattern**: All configuration via `shared/config.py` Pydantic Settings (environment variables)
2. **Repository Pattern**: `dynamo_repository.py` abstracts DynamoDB operations
3. **Factory Pattern**: Voice client instantiation based on `VOICE_PROVIDER` config
4. **Async Context Managers**: Voice clients use `async with` for connection lifecycle
5. **Correlation IDs**: All logs include `call_sid`, `stream_sid`, `conversation_id`, `handover_id`

### Audio Format Notes

- **Twilio**: Sends/receives G.711 μ-law 8kHz (base64-encoded)
- **OpenAI Realtime**: Expects PCM16 (conversion needed - not currently implemented)
- **Nova 2 Sonic**: Native G.711 μ-law 8kHz (no conversion needed)

**When adding audio conversion**: Implement in `stream_handler.py` before sending to OpenAI client.

## Configuration Management

All configuration is via **environment variables** loaded by Pydantic Settings in `shared/config.py`. No secrets in code or `.env` files in production.

### Critical Environment Variables

- `USE_PIPECAT`: `true` (default) or `false` - Use Pipecat framework
- `VOICE_PROVIDER`: `openai` or `nova` (determines which voice AI service to use)
- `PUBLIC_HOST`: Public hostname for Twilio webhooks (e.g., ngrok domain)
- `OPENAI_API_KEY`: Required if `VOICE_PROVIDER=openai`
- `AWS_REGION`: Region for DynamoDB/Lambda (any AWS region)
- `NOVA_REGION`: Region for Nova 2 Sonic (must be supported region if `VOICE_PROVIDER=nova`)
- `DYNAMODB_ENDPOINT_URL`: Use `http://dynamodb-local:8000` for local dev
- `USE_LOCAL_DYNAMODB=true`: Enables local DynamoDB (skips table creation checks)

### Local vs Production

**Local** (`.env`):
```bash
USE_LOCAL_DYNAMODB=true
DYNAMODB_ENDPOINT_URL=http://localhost:8001
PUBLIC_HOST=your-subdomain.ngrok.io
```

**Production** (AWS Secrets Manager or Parameter Store):
```bash
USE_LOCAL_DYNAMODB=false
# DYNAMODB_ENDPOINT_URL not set (uses default AWS endpoint)
PUBLIC_HOST=voice-gateway.example.com
```

## Testing Strategy

### Test Markers

- `@pytest.mark.unit`: Fast unit tests (always run in CI)
- `@pytest.mark.integration`: Integration tests with DynamoDB Local
- `@pytest.mark.deepeval`: LLM-based prompt evaluation (requires `OPENAI_API_KEY`, optional in CI)

### When to Mock

- **Always mock**: OpenAI WebSocket, Nova Bedrock client, HubSpot API, Twilio API, external network calls
- **Use real clients**: DynamoDB Local (via `moto` or docker container)
- **Never mock**: Internal modules (`token_generator`, `escalation`, `prompts`)

### Running Tests in CI

GitHub Actions workflow (`.github/workflows/ci.yml`):
```yaml
- run: pytest tests/unit -m "not deepeval"  # Fast tests always run
- run: pytest tests/unit -m deepeval        # Optional, if OPENAI_API_KEY set
```

## AWS Infrastructure (Terraform)

The `terraform/` directory contains production infrastructure:

- **ECS Fargate**: Gateway service with auto-scaling
- **ALB**: Application Load Balancer with WebSocket support
- **DynamoDB**: Tokens table with TTL enabled
- **ECR**: Container registry for gateway image
- **IAM**: Task execution roles and policies

**Deployment steps**:
1. Build and push Docker image to ECR
2. Run `terraform apply` to provision infrastructure
3. Update Twilio webhook to ALB DNS name
4. Deploy Lambda function separately (see `aws/connect_lambda/`)

**Terraform state**: Stored in S3 backend (see `backend.hcl`). Initialize with `terraform init -backend-config=backend.hcl`.

## Twilio Integration

### Webhook Flow

1. **Incoming call**: `POST /twilio/voice` returns TwiML with `<Stream>` directive
2. **WebSocket**: Twilio connects to `wss://{PUBLIC_HOST}/twilio/stream`
3. **Events**: `start`, `media` (audio chunks), `stop`
4. **Audio format**: G.711 μ-law 8kHz, base64-encoded in `media.payload`

**Critical**: The `PUBLIC_HOST` must be publicly accessible (use ngrok for local dev). Twilio requires TLS (wss://) in production.

## Voice Provider Details

### OpenAI Realtime

- **Connection**: WebSocket to `wss://api.openai.com/v1/realtime`
- **Authentication**: API key in query param or header
- **Events**: `session.update`, `input_audio_buffer.append`, `response.audio.delta`, `conversation.item.input_audio_transcription.completed`
- **Session config**: Modalities, voice, VAD settings sent on connection

**Rate limits**: Requests per minute and tokens per minute (account tier dependent).

### Amazon Nova 2 Sonic

- **Connection**: Bidirectional stream via `boto3` Bedrock Runtime client
- **Method**: `invoke_model_with_bidirectional_stream()`
- **Model ID**: `amazon.nova-sonic-v1:0`
- **Events**: `sessionStart`, `audioChunk`, `outputAudioDelta`, `inputTranscript`, `outputTranscriptDelta`
- **Languages**: English, French, Italian, German, Spanish, Portuguese, Hindi

**Permissions**: Requires `bedrock:InvokeModelWithResponseStream` on `arn:aws:bedrock:*::foundation-model/amazon.nova-sonic-v1:0`.

## HubSpot Integration

Optional (controlled by `ENABLE_HUBSPOT` env var). Creates contact and ticket during escalation.

**API endpoints**:
- `POST /crm/v3/objects/contacts/search`: Find existing contact by phone
- `POST /crm/v3/objects/contacts`: Create contact
- `POST /crm/v3/objects/tickets`: Create ticket
- `PUT /crm/v4/associations/tickets/contacts/batch/create`: Associate ticket with contact

**Retry policy**: Exponential backoff (1s, 2s, 4s, 8s, 10s), max 5 attempts, retry on 429 and 5xx.

**When HubSpot fails**: Escalation continues (logged as warning). Token still stored in DynamoDB.

## Logging & Monitoring

All logs are **structured JSON** with correlation IDs. Use `shared/logging.py` logger:

```python
from shared.logging import get_logger
logger = get_logger(__name__)

logger.info("Escalation triggered", extra={
    "call_sid": call_sid,
    "stream_sid": stream_sid,
    "conversation_id": conversation_id,
    "handover_id": token
})
```

**Never log**: Full transcripts (PII), API keys, AWS credentials. Phone numbers are OK per requirements.

### Key Metrics to Monitor

- Active sessions count (gauge)
- Escalation rate (counter)
- Voice provider connection failures (counter by provider)
- DynamoDB throttles (CloudWatch metric)
- Lambda invocation errors (CloudWatch Logs)

## Common Troubleshooting

### "ModuleNotFoundError"
Run `pip install -e ".[dev]"` to install all dependencies.

### "Connection refused" on localhost:8000
Check `docker-compose ps` or `curl http://localhost:8000/health`.

### "OpenAI WebSocket failed to connect"
Verify `OPENAI_API_KEY` is valid. Check https://status.openai.com.

### "Model not found in region" (Nova 2)
Ensure `NOVA_REGION` is `us-east-1`, `eu-north-1`, or `ap-northeast-1`.

### "Twilio webhook timeout"
- Verify ngrok is running: `ngrok http 8000`
- Update `PUBLIC_HOST` in `.env` with ngrok URL
- Restart gateway: `docker-compose restart gateway`

### "Lambda not finding token"
- Check DynamoDB table exists and has TTL enabled
- Verify token is being stored (check CloudWatch Logs for gateway)
- Ensure Lambda has read permissions on DynamoDB table

## Security Considerations

- **API keys**: Use environment variables or AWS Secrets Manager (never commit to Git)
- **Webhook validation**: Twilio signature verification not implemented (add in production)
- **TLS**: Twilio requires HTTPS/WSS in production (terminate at ALB)
- **IAM**: Use least privilege roles (task execution role for ECS, Lambda execution role)
- **DynamoDB**: Token TTL ensures automatic expiry (10 minutes)
- **Network**: Deploy gateway in private subnet with ALB in public subnet

## Performance & Scaling

- **Async I/O**: Gateway uses `asyncio` for concurrent call handling
- **Horizontal scaling**: Deploy multiple ECS tasks behind ALB with sticky sessions
- **DynamoDB**: Use on-demand billing or provisioned with auto-scaling
- **Rate limits**: Monitor OpenAI/Bedrock quotas and implement backpressure if needed
- **Memory**: Each active session consumes ~10-20MB (plan ECS task size accordingly)

## Documentation References

- [README.md](README.md) - Complete system overview and setup
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed component design and data flows
- [GETTING_STARTED.md](GETTING_STARTED.md) - Step-by-step local development setup
- [NOVA_SONIC_INTEGRATION.md](NOVA_SONIC_INTEGRATION.md) - Nova 2 Sonic provider details
- [PROMPT_TESTING_GUIDE.md](PROMPT_TESTING_GUIDE.md) - AI prompt testing with DeepEval
- [terraform/DEPLOYMENT_GUIDE.md](terraform/DEPLOYMENT_GUIDE.md) - Production deployment steps
- [services/orchestrator/README_PROMPTS.md](services/orchestrator/README_PROMPTS.md) - Prompt configuration details
