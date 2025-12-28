# Amazon Nova 2 Sonic Integration

This document describes the integration of Amazon Nova 2 Sonic as an alternative voice provider to OpenAI Realtime.

## Status: ✅ Production Ready

**Current Status**: Both OpenAI Realtime and Amazon Nova 2 Sonic are fully integrated and production-ready. Switch between providers using the `VOICE_PROVIDER` environment variable.

## Overview

The system supports two voice AI providers:
- **OpenAI Realtime API** (active) - GPT-4o with real-time speech-to-speech
- **Amazon Nova 2 Sonic** (active) - AWS Bedrock's next-generation speech-to-speech model

## Why Nova 2 Sonic?

Amazon Nova 2 Sonic offers several advantages over Nova 1 and OpenAI:

1. **Native AWS Integration**: Seamless integration with Amazon Connect, DynamoDB, and other AWS services
2. **Enhanced Telephony Support**: Native support for 8KHz telephony input (perfect for Twilio)
3. **Multi-language Support**: 7 languages with polyglot voices (English, French, Italian, German, Spanish, Portuguese, Hindi)
4. **Crossmodal Interactions**: Switch between text and voice within the same session
5. **Improved Speech Understanding**: Better handling of alphanumeric inputs, accents, and background noise
6. **AWS Ecosystem**: Stay within AWS for simplified billing and IAM management
7. **Cost Effective**: Industry-leading price performance

## Implementation Details

Amazon Nova 2 Sonic uses a **bidirectional streaming API** (`InvokeModelWithBidirectionalStream`) via the AWS SDK:

- **SDK**: `boto3` with `bedrock-runtime`
- **Status**: Production-ready
- **Implementation**: Complete `NovaClient` implementation with full audio streaming support

The voice client infrastructure is complete with both `OpenAIRealtimeClient` and `NovaClient` implementations.

## Configuration

### Environment Variables

Set the voice provider in your `.env` file:

```bash
# Voice Provider Configuration
VOICE_PROVIDER=nova  # Options: "openai" or "nova"

# OpenAI Configuration (only needed if VOICE_PROVIDER=openai)
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxx

# AWS Configuration (required for both providers)
AWS_REGION=ap-southeast-2      # For DynamoDB and Lambda (can be any region)
NOVA_REGION=us-east-1          # For Nova 2 Sonic model (must be a supported region)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

### Regional Availability

Nova 2 Sonic is available in these AWS regions:
- `us-east-1` (US East - N. Virginia)
- `eu-north-1` (Europe - Stockholm)
- `ap-northeast-1` (Asia Pacific - Tokyo)

**Important**: Set `NOVA_REGION` to one of these regions. The `AWS_REGION` variable is used for DynamoDB and Lambda, and can be set to any AWS region to optimize for latency and compliance.

### Multi-Region Architecture

The system supports deploying resources in different regions:

- **NOVA_REGION**: Where the Nova 2 Sonic model runs (limited to supported regions)
- **AWS_REGION**: Where DynamoDB and Lambda are deployed (any AWS region)

Example configuration for Australian deployment:
```bash
VOICE_PROVIDER=nova
AWS_REGION=ap-southeast-2      # Sydney - for DynamoDB, Lambda, Amazon Connect
NOVA_REGION=ap-northeast-1     # Tokyo - closest Nova 2 region
```

This allows you to:
1. Keep data in your preferred region for compliance
2. Minimize latency to Amazon Connect
3. Use Nova 2 Sonic from the nearest supported region

## IAM Permissions

Your AWS credentials need the following permissions for Nova Sonic:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/amazon.nova-sonic-v1:0"
      ]
    }
  ]
}
```

## Architecture

The integration uses an abstract base class (`VoiceClientBase`) that both providers implement:

```
┌─────────────────────┐
│  VoiceClientBase    │  (Abstract Interface)
│  - connect()        │
│  - send_audio()     │
│  - events()         │
│  - cancel_response()│
│  - close()          │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼───────┐ ┌──▼────────────┐
│ OpenAI    │ │ Nova Sonic    │
│ Realtime  │ │ (Bedrock)     │
└───────────┘ └───────────────┘
```

## How It Works

### 1. Audio Flow

```
Twilio (G.711 μ-law) → Gateway → Voice Provider → Gateway → Twilio
                                       ↓
                                  Transcripts
                                       ↓
                                  Escalation
                                    Detection
```

### 2. Event Normalization

Nova Sonic events are normalized to match OpenAI's event format for compatibility:

**Nova Sonic Event**:
```json
{
  "outputAudioDelta": {
    "format": "audio/g711-mulaw",
    "data": "hex_encoded_audio"
  }
}
```

**Normalized to**:
```json
{
  "type": "response.audio.delta",
  "delta": "base64_encoded_audio"
}
```

This allows the same `StreamHandler` to work with both providers without modification.

### 3. Session Configuration

Nova Sonic sessions are configured with:
- **Mode**: realtime (bidirectional streaming)
- **Audio Encoding**: G.711 μ-law at 8 kHz
- **Transcription**: Enabled for escalation detection
- **Response Modality**: Speech + text
- **System Prompt**: From your assistant prompt configuration

## Switching Providers

To switch between providers:

1. **Switch to Nova Sonic**:
   ```bash
   # In .env file
   VOICE_PROVIDER=nova
   AWS_REGION=ap-southeast-2  # Your preferred region for DynamoDB/Lambda
   NOVA_REGION=us-east-1      # Must be a Nova-supported region
   ```

2. **Switch back to OpenAI**:
   ```bash
   # In .env file
   VOICE_PROVIDER=openai
   OPENAI_API_KEY=your-api-key
   ```

3. **Rebuild containers**:
   ```bash
   docker-compose down
   docker-compose up --build -d
   ```

## Testing

Test the integration:

1. Make a call to your Twilio number
2. Check logs for voice provider initialization:
   ```
   INFO: Using Amazon Nova Sonic voice provider
   ```
3. Verify bidirectional audio works
4. Test escalation flow to Amazon Connect

## Limitations

### Nova Sonic

- **Session Duration**: 8 minutes per session (can be renewed)
- **Audio Format**: Only G.711 μ-law at 8 kHz (matches Twilio perfectly)
- **Text-to-Speech Trigger**: Currently uses system prompt modification (not as elegant as OpenAI's direct text input)

### OpenAI Realtime

- **Smaller Context**: Limited context window compared to Nova Sonic
- **Cross-Cloud**: Requires managing credentials across AWS and OpenAI

## Cost Comparison

### Nova Sonic Pricing
- Input audio: $0.000064 per second
- Output audio: $0.000192 per second
- Text tokens: Standard Bedrock rates

### OpenAI Realtime Pricing
- Audio input: $0.06 per minute
- Audio output: $0.24 per minute
- Cached input: $0.015 per minute

**Example**: 10-minute call
- **Nova Sonic**: ~$1.50
- **OpenAI**: ~$3.00

## Troubleshooting

### "Model not found in region"
- Ensure `NOVA_REGION` is set to `us-east-1`, `eu-north-1`, or `ap-northeast-1`
- Note that `AWS_REGION` (for DynamoDB/Lambda) can be different

### "AccessDeniedException"
- Check IAM permissions include `bedrock:InvokeModelWithResponseStream`
- Verify AWS credentials are configured correctly

### "No audio output"
- Check logs for streaming errors
- Verify network connectivity to AWS Bedrock endpoints
- Ensure G.711 μ-law audio format compatibility

### "Model timeout"
- Network latency to Bedrock region may be high
- Consider using a region closer to your deployment
- Check AWS service health dashboard

## Future Enhancements

Potential improvements:
1. **Pinecone Integration**: Add RAG capabilities for knowledge retrieval
2. **Multi-language Support**: Expose language configuration via API
3. **Voice Cloning**: Support custom voice profiles
4. **Function Calling**: Add tool use capabilities to Nova Sonic
5. **Hybrid Mode**: Use both providers simultaneously for A/B testing

## References

- [Amazon Nova Sonic Documentation](https://docs.aws.amazon.com/nova/latest/userguide/speech.html)
- [AWS Bedrock Streaming API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-streaming.html)
- [Nova Sonic Telephony Integration Guide](https://aws.amazon.com/blogs/machine-learning/building-ai-powered-voice-applications-amazon-nova-sonic-telephony-integration-guide/)
- [Nova Sonic Announcement](https://aws.amazon.com/blogs/aws/introducing-amazon-nova-2-sonic-next-generation-speech-to-speech-model-for-conversational-ai/)
