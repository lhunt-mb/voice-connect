# Pipecat Integration

This module provides the Pipecat-based implementation of the voice AI pipeline, offering a cleaner and more maintainable architecture for voice conversations.

## Overview

[Pipecat](https://www.pipecat.ai/) is an open-source Python framework for building real-time voice and multimodal conversational agents. This integration leverages Pipecat to:

- Simplify audio pipeline orchestration
- Provide native support for OpenAI Realtime API and Amazon Nova 2 Sonic
- Handle Twilio WebSocket media streams with built-in serializers
- Enable modular, testable pipeline components

## Architecture

```
Twilio WebSocket
       │
       ▼
┌──────────────────────────────────────────────────┐
│           FastAPIWebsocketTransport               │
│        (TwilioFrameSerializer + VAD)              │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│              Voice AI Service                     │
│    (OpenAI Realtime OR Nova 2 Sonic)             │
│         - Native audio-in/audio-out               │
│         - Built-in transcription                  │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│           EscalationProcessor                     │
│    - Keyword detection from transcripts           │
│    - Triggers escalation workflow                 │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│              Transport Output                     │
│         (Audio back to Twilio)                    │
└──────────────────────────────────────────────────┘
```

## Components

### Pipeline Factory (`pipeline_factory.py`)

Creates configured voice AI pipelines with:
- Provider-agnostic interface (OpenAI Realtime or Nova Sonic)
- Twilio-compatible WebSocket transport
- Voice Activity Detection (VAD) using Silero
- Escalation processor integration

```python
from services.pipecat import create_voice_pipeline, PipelineConfig

config = PipelineConfig(
    provider="openai",  # or "nova"
    prompt=get_prompt("default"),
    session=session,
    on_escalation=orchestrator.check_and_handle_escalation,
)

components = await create_voice_pipeline(
    websocket=websocket,
    stream_sid=stream_sid,
    call_sid=call_sid,
    settings=settings,
    config=config,
)

await run_pipeline(components)
```

### Escalation Processor (`escalation_processor.py`)

A Pipecat `FrameProcessor` that:
- Monitors transcription frames for escalation keywords
- Triggers the escalation workflow when detected
- Sends a transfer message to the user
- Ends the conversation gracefully

## Configuration

Enable Pipecat mode via environment variable:

```bash
USE_PIPECAT=true  # Default is true
```

Or disable to use the legacy implementation:

```bash
USE_PIPECAT=false
```

## Voice Providers

### OpenAI Realtime API

```bash
VOICE_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Features:
- Native G.711 μ-law audio support
- Built-in Whisper transcription
- Server-side VAD

### Amazon Nova 2 Sonic

```bash
VOICE_PROVIDER=nova
NOVA_REGION=us-east-1  # Must be us-east-1, eu-north-1, or ap-northeast-1
```

Features:
- Native multimodal audio-in/audio-out
- No separate STT/TTS required
- Configurable endpointing sensitivity

## RAG Integration (Future)

Pipecat supports RAG integration through two patterns:

### 1. Function Calling (Recommended)

Register a function that queries your vector database:

```python
from pipecat.services.llm_service import FunctionCallParams

async def search_knowledge_base(params: FunctionCallParams):
    query = params.arguments.get("query")
    results = await vector_store.similarity_search(query, k=5)
    context = "\n".join([doc.page_content for doc in results])
    await params.result_callback({"context": context})

llm.register_function("search_knowledge_base", search_knowledge_base)
```

### 2. Custom Frame Processor

Intercept transcriptions and inject context:

```python
class RAGProcessor(FrameProcessor):
    async def process_frame(self, frame, direction):
        if isinstance(frame, TranscriptionFrame):
            results = await self.vector_store.similarity_search(frame.text)
            if results:
                context_frame = LLMMessagesAppendFrame(
                    messages=[{"role": "system", "content": f"<context>{results}</context>"}]
                )
                await self.push_frame(context_frame, direction)
        await self.push_frame(frame, direction)
```

## Testing

Run Pipecat-specific tests:

```bash
pytest tests/unit/test_pipecat_pipeline.py -v
```

## Migration Guide

### From Legacy to Pipecat

1. Set `USE_PIPECAT=true` in your environment
2. No code changes required - the gateway auto-selects the implementation
3. Existing escalation workflows continue to work
4. Session management is unchanged

### Key Differences

| Aspect | Legacy | Pipecat |
|--------|--------|---------|
| Audio handling | Manual event loops | Pipeline processors |
| Escalation | StreamHandler method | EscalationProcessor |
| VAD | Provider-specific | Silero (unified) |
| Code complexity | Higher | Lower |
| Testability | Harder to mock | Easier to test |

## Troubleshooting

### "Module not found: pipecat"

Install Pipecat dependencies:

```bash
pip install -e ".[dev]"
```

### "Nova Sonic connection failed"

Ensure NOVA_REGION is set to a supported region:
- us-east-1
- eu-north-1
- ap-northeast-1

### "Transcription not triggering escalation"

Check that the escalation processor is in the pipeline:

```python
# Verify escalation_processor is not None
assert components.escalation_processor is not None
```
