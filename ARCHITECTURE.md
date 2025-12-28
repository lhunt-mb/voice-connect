# Architecture Documentation

## System Overview

The Voice OpenAI Connect system implements a Pattern A enterprise voice AI architecture with the following key components:

1. **AI Voice Gateway** - FastAPI service handling Twilio WebSocket streams
2. **Orchestrator** - Business logic for conversation management and escalation
3. **Voice Client** - Pluggable voice provider (OpenAI Realtime API or Amazon Nova 2 Sonic)
4. **DynamoDB** - Token storage with TTL for handover context
5. **HubSpot Integration** - CRM contact and ticket management
6. **Amazon Connect Lambda** - Token validation and attribute retrieval

## Component Details

### 1. AI Voice Gateway (FastAPI)

**Location**: `services/gateway/`

**Responsibilities**:
- Accept Twilio voice webhooks and return TwiML
- Handle Twilio Media Streams WebSocket connections
- Manage per-session state (SessionManager)
- Bridge audio between Twilio and OpenAI (StreamHandler)

**Key Flows**:

```
Incoming Call:
  POST /twilio/voice
    ├─> Extract CallSid, From
    ├─> Generate TwiML with <Stream> directive
    └─> Return TwiML response

WebSocket Stream:
  WS /twilio/stream
    ├─> Accept connection
    ├─> Wait for 'start' event
    ├─> Create session (SessionManager)
    ├─> Initialize voice client (OpenAI or Nova 2)
    ├─> Start StreamHandler
    │   ├─> Handle Twilio events (start, media, stop)
    │   ├─> Forward audio to voice provider
    │   ├─> Receive voice provider events
    │   ├─> Send audio back to Twilio
    │   └─> Check escalation on transcripts
    └─> Cleanup on disconnect
```

### 2. Orchestrator

**Location**: `services/orchestrator/`

**Responsibilities**:
- Manage conversation state and metadata
- Implement escalation policies (keyword detection)
- Coordinate integrations (HubSpot, Twilio, DynamoDB)
- Generate handover tokens
- Execute escalation workflow

**Escalation Workflow**:

```
1. Detect escalation trigger
   ├─> Keyword match in transcript
   └─> Or agent decision/error

2. Generate token
   └─> 10-digit numeric token

3. Create HubSpot records
   ├─> Upsert contact by phone
   ├─> Create ticket
   └─> Add metadata note

4. Store in DynamoDB
   ├─> Token → payload mapping
   └─> TTL = 10 minutes

5. Initiate Connect call
   ├─> Call Connect phone number
   ├─> Send DTMF token (wwww + digits + #)
   └─> Return control

6. End bot session
   └─> Close voice client connection
```

### 3. Voice Client

**Location**: `services/orchestrator/`

The system supports two voice providers through a common `VoiceClientBase` interface:

#### 3a. OpenAI Realtime Client

**Location**: `services/orchestrator/openai_realtime.py`

**Responsibilities**:
- Establish WebSocket connection to OpenAI Realtime API
- Send session configuration (modalities, voice, VAD settings)
- Stream audio input frames (base64-encoded PCM16)
- Receive and queue audio output frames
- Receive transcripts and events

**Message Format**:

```
Outbound (to OpenAI):
  - session.update: Configure session
  - input_audio_buffer.append: Send audio data (base64)

Inbound (from OpenAI):
  - response.audio.delta: Audio response chunks
  - conversation.item.input_audio_transcription.completed: User transcript
  - response.done: Response completed
  - error: Error events
```

#### 3b. Amazon Nova 2 Sonic Client

**Location**: `services/orchestrator/nova_client.py`

**Responsibilities**:
- Establish bidirectional stream with AWS Bedrock Runtime
- Send session configuration (audio format, system prompt)
- Stream audio input frames (G.711 μ-law, native Twilio format)
- Receive and queue audio output frames
- Receive transcripts and events

**Message Format**:

```
Outbound (to Nova):
  - sessionStart: Configure session with audio format and system prompt
  - audioChunk: Send audio data (hex-encoded G.711 μ-law)

Inbound (from Nova):
  - outputAudioDelta: Audio response chunks (G.711 μ-law)
  - outputTranscriptDelta: AI transcript text
  - inputTranscript: User transcript
  - sessionEnd: Session completed
```

**Key Advantages**:
- Native G.711 μ-law support (no audio conversion needed for Twilio)
- Multi-language support (7 languages including English, French, Spanish, German, Italian, Portuguese, Hindi)
- Seamless AWS integration with Amazon Connect and DynamoDB
- 8 kHz telephony audio optimized for voice calls

### 4. DynamoDB Repository

**Location**: `services/orchestrator/dynamo_repository.py`

**Table Schema**:

```
Table: HandoverTokens
PK: token (String)

Attributes:
  - token: string (10 digits)
  - conversation_id: string (UUID)
  - created_at: string (ISO timestamp)
  - expires_at: number (epoch seconds, TTL attribute)
  - caller_phone: string (E.164 format)
  - hubspot_contact_id: string
  - hubspot_ticket_id: string
  - summary: string
  - intent: string
  - priority: string
  - escalation_reason: string
```

**TTL Configuration**:
- DynamoDB automatically deletes items when `expires_at` < current time
- Set to 10 minutes after creation
- Prevents token reuse and reduces storage

### 5. HubSpot Client

**Location**: `services/orchestrator/hubspot_client.py`

**API Endpoints Used**:

```
POST /crm/v3/objects/contacts/search
  └─> Search for existing contact by phone

POST /crm/v3/objects/contacts
  └─> Create new contact

POST /crm/v3/objects/tickets
  └─> Create ticket

PUT /crm/v4/associations/tickets/contacts/batch/create
  └─> Associate ticket with contact

POST /crm/v3/objects/notes
  └─> Create note

PUT /crm/v4/associations/notes/tickets/batch/create
  └─> Associate note with ticket
```

**Retry Policy**:
- Exponential backoff: 1s, 2s, 4s, 8s, 10s
- Retry on 429 (rate limit) and 5xx errors
- Max 5 attempts

### 6. Amazon Connect Lambda

**Location**: `aws/connect_lambda/handler.py`

**Invocation**:
- Triggered by Connect contact flow
- Receives token from Store Customer Input block
- Returns attributes for Set Contact Attributes block

**Input Event**:

```json
{
  "Details": {
    "ContactData": {
      "ContactId": "...",
      "Channel": "VOICE",
      ...
    },
    "Parameters": {
      "token": "1234567890"
    }
  }
}
```

**Output**:

```json
{
  "success": true,
  "conversation_id": "uuid",
  "caller_phone": "+61...",
  "hubspot_contact_id": "...",
  "hubspot_ticket_id": "...",
  "summary": "...",
  "intent": "...",
  "priority": "high",
  "escalation_reason": "user_request",
  "route_to_queue": "escalation"
}
```

## Data Flow

### Audio Streaming

```
┌─────────┐         ┌─────────┐         ┌──────────────┐
│ Twilio  │         │ Gateway │         │Voice Provider│
└─────────┘         └─────────┘         └──────────────┘
     │                   │                      │
     │  media (base64)   │                      │
     ├──────────────────►│                      │
     │                   │  audio data          │
     │                   ├─────────────────────►│
     │                   │                      │
     │                   │  audio.delta         │
     │                   │◄─────────────────────┤
     │  media (base64)   │                      │
     │◄──────────────────┤                      │
     │                   │                      │
```

**Audio Format Notes**:
- **Twilio**: Sends/receives G.711 μ-law 8kHz (base64-encoded)
- **OpenAI Realtime**: Expects PCM16 (audio format conversion needed)
- **Nova 2 Sonic**: Native G.711 μ-law 8kHz support (no conversion needed, ideal for telephony)

### Escalation Flow

```
┌──────┐  ┌──────────┐  ┌─────────┐  ┌────────┐  ┌─────────┐
│ User │  │ Gateway  │  │Orchestr.│  │HubSpot │  │DynamoDB │
└──────┘  └──────────┘  └─────────┘  └────────┘  └─────────┘
   │           │             │            │            │
   ├─"agent"──►│             │            │            │
   │           ├──transcript►│            │            │
   │           │             ├──check─────┤            │
   │           │             │            │            │
   │           │             ├──generate token         │
   │           │             │                         │
   │           │             ├──upsert contact────────►│
   │           │             │◄──contact_id────────────┤
   │           │             │                         │
   │           │             ├──create ticket─────────►│
   │           │             │◄──ticket_id─────────────┤
   │           │             │                         │
   │           │             ├──store token───────────►│
   │           │             │                         │
   │           │◄──escalate──┤                         │
   │           │             │                         │
   │           ├──close AI───┤                         │
   │◄──end call┤             │                         │
```

## Concurrency Model

### Async Architecture

All I/O operations are async to support concurrent sessions:

```python
# Multiple calls handled concurrently
async def handle_call_1():
    async with openai_client as client:
        async for event in client.events():
            ...

async def handle_call_2():
    async with openai_client as client:
        async for event in client.events():
            ...

# Run concurrently
await asyncio.gather(handle_call_1(), handle_call_2())
```

### Session Isolation

Each call has isolated state:

```
SessionManager
  ├─> session[stream_sid_1]
  │     ├─> conversation_id
  │     ├─> openai_client
  │     └─> transcript_buffer
  ├─> session[stream_sid_2]
  │     ├─> conversation_id
  │     ├─> openai_client
  │     └─> transcript_buffer
  └─> session[stream_sid_n]
```

### Resource Management

- Voice Provider Connection: One per active call (WebSocket for OpenAI, bidirectional stream for Nova 2)
- Twilio WebSocket: One per active call
- DynamoDB: Shared client with connection pooling
- HubSpot: Shared async HTTP client
- AWS Bedrock (Nova 2): Shared client with async streaming support

## Error Handling

### Voice Provider Disconnect

```
if voice_provider_connection_closed:
  ├─> Log error
  ├─> Send fallback message to user
  ├─> Optionally trigger escalation
  └─> Clean up resources
```

### Twilio Disconnect

```
if twilio_websocket_disconnected:
  ├─> Log event
  ├─> Close voice provider connection
  ├─> Remove session from manager
  └─> Clean up resources
```

### Escalation Failures

```
if hubspot_create_fails:
  └─> Log error, continue with escalation

if dynamodb_put_fails:
  └─> Log error, abort escalation

if connect_call_fails:
  └─> Log error, token still valid
```

## Scaling Considerations

### Horizontal Scaling

Gateway service is stateless (except in-memory sessions):
- Scale with container count
- Use sticky sessions at load balancer for WebSocket connections
- Consider Redis for distributed session state

### DynamoDB

- Use on-demand billing or provisioned with autoscaling
- Monitor throttling metrics
- Consider GSI for query patterns (e.g., by conversation_id)

### Rate Limits

- **OpenAI Realtime**: Requests per minute, tokens per minute (account tier dependent)
- **Nova 2 Sonic**: AWS Bedrock service quotas and throttling limits
- **HubSpot**: 100 requests per 10 seconds (burst)
- **Twilio**: Account-specific limits

## Security

### Authentication

- **Twilio**: Verify webhook signatures (not implemented, add in production)
- **OpenAI Realtime**: API key in Authorization header
- **Nova 2 Sonic**: AWS credentials (IAM roles or access keys) with Bedrock permissions
- **HubSpot**: Private app token
- **AWS Services**: IAM roles or access keys

### Data Protection

- No PII in logs (phone numbers are OK per requirement)
- No full transcripts stored
- Tokens expire after 10 minutes
- TLS for all external communication

### Network

- Deploy in private subnet (except gateway ingress)
- Use VPC endpoints for AWS services
- Restrict security groups to necessary ports

## Monitoring

### Metrics

```
- gateway_active_sessions (gauge)
- gateway_escalations_total (counter)
- gateway_session_duration_seconds (histogram)
- voice_provider_connection_failures_total (counter)
- voice_provider_type (gauge: openai or nova)
- dynamodb_throttles_total (counter)
- lambda_invocations_total (counter)
- lambda_errors_total (counter)
```

### Logging

All logs include correlation IDs:
- call_sid
- stream_sid
- conversation_id
- handover_id

### Tracing

Consider adding distributed tracing:
- OpenTelemetry
- AWS X-Ray
- Trace entire call flow from Twilio → Gateway → Voice Provider → Connect

## Testing Strategy

### Unit Tests

- Token generation and validation
- Escalation keyword detection
- Voice client abstraction and provider selection
- DynamoDB repository operations (mocked)
- HubSpot client requests (mocked)
- Lambda handler logic

### Integration Tests

- Gateway HTTP endpoints
- WebSocket connection flow
- DynamoDB operations (local DynamoDB)
- End-to-end escalation (mocked external services)

### Load Tests

- Concurrent WebSocket connections
- Session creation/cleanup
- DynamoDB throughput
- Memory usage under load

## Voice Provider Selection

The system uses a factory pattern to instantiate the appropriate voice client based on the `VOICE_PROVIDER` environment variable:

```python
# In orchestrator or gateway
if config.voice_provider == "openai":
    voice_client = OpenAIRealtimeClient(api_key=config.openai_api_key)
elif config.voice_provider == "nova":
    voice_client = NovaClient(region=config.aws_region)
```

Both clients implement the `VoiceClientBase` interface:
- `connect()`: Establish connection to provider
- `send_audio(audio_data)`: Stream audio to provider
- `events()`: Async iterator for receiving events
- `cancel_response()`: Interrupt current AI response
- `close()`: Clean up connection

This abstraction allows seamless switching between providers without modifying the gateway or stream handler logic.

## Future Enhancements

1. **Audio Format Conversion**: Implement mulaw ↔ PCM16 conversion for OpenAI (already native for Nova 2)
2. **Sentiment Analysis**: Proactive escalation based on sentiment
3. **Call Recording**: Store audio for compliance (S3 + encryption)
4. **Agent Availability**: Check Connect queue before escalation
5. **Callback**: Offer callback instead of immediate transfer
6. **Multi-language**: Expose Nova 2's multi-language support via API
7. **Custom Tools**: Function calling for specific actions (both providers support this)
8. **Metrics Dashboard**: Real-time dashboard for operations
9. **Hybrid Mode**: A/B testing with both providers simultaneously
