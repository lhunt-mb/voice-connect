"""Factory for creating Pipecat voice AI pipelines.

This module provides a unified interface for creating voice AI pipelines
using either OpenAI Realtime API or Amazon Nova 2 Sonic, with Twilio
as the telephony transport.
"""

import logging
import os
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from pipecat.frames.frames import EndFrame, LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from services.orchestrator.prompts import AssistantPrompt
from services.pipecat.escalation_processor import EscalationProcessor
from shared.config import Settings
from shared.types import SessionState

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for creating a voice AI pipeline.

    Attributes:
        provider: Voice AI provider ("openai" or "nova")
        prompt: Assistant prompt configuration
        session: Session state for the call
        on_escalation: Callback when escalation is triggered
        vad_stop_secs: Seconds of silence before VAD triggers end of speech
    """

    provider: str
    prompt: AssistantPrompt
    session: SessionState
    on_escalation: Callable[[SessionState, str], Coroutine[Any, Any, bool]] | None = None
    vad_stop_secs: float = 0.5


@dataclass
class PipelineComponents:
    """Container for pipeline components.

    Holds references to the key components needed for pipeline lifecycle management.
    """

    transport: FastAPIWebsocketTransport
    pipeline: Pipeline
    task: PipelineTask
    runner: PipelineRunner
    escalation_processor: EscalationProcessor | None = None
    llm_service: Any = None


def _create_openai_realtime_service(settings: Settings, prompt: AssistantPrompt) -> Any:
    """Create OpenAI Realtime LLM service.

    Args:
        settings: Application settings
        prompt: Assistant prompt configuration

    Returns:
        Configured OpenAI Realtime service
    """
    from pipecat.services.openai.realtime.events import (
        AudioConfiguration,
        AudioInput,
        InputAudioTranscription,
        SessionProperties,
        TurnDetection,
    )
    from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService

    # Configure audio with transcription and turn detection
    # This is required for escalation detection to work
    audio_config = AudioConfiguration(
        input=AudioInput(
            # Use whisper-1 for input transcription (required for escalation detection)
            transcription=InputAudioTranscription(model="whisper-1"),
            turn_detection=TurnDetection(
                type="server_vad",
                threshold=0.5,
                prefix_padding_ms=300,
                silence_duration_ms=500,
            ),
        ),
    )

    # Session properties with audio configuration
    session_properties = SessionProperties(
        model="gpt-4o-realtime-preview",
        instructions=prompt.instructions,
        audio=audio_config,
    )

    api_key = settings.openai_api_key or ""
    service = OpenAIRealtimeLLMService(
        api_key=api_key,
        session_properties=session_properties,
        start_audio_paused=False,
    )

    return service


def _create_nova_sonic_service(settings: Settings, prompt: AssistantPrompt) -> Any:
    """Create Amazon Nova 2 Sonic LLM service.

    Args:
        settings: Application settings
        prompt: Assistant prompt configuration

    Returns:
        Configured Nova Sonic service
    """
    from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params

    # Nova Sonic region (must be us-east-1, eu-north-1, or ap-northeast-1)
    nova_region = settings.nova_region or settings.aws_region or "us-east-1"

    # Map OpenAI voices to Nova Sonic voices
    voice_mapping = {
        "alloy": "olivia",
        "echo": "matteo",
        "shimmer": "tiffany",
        "verse": "matthew",
    }
    nova_voice = voice_mapping.get(prompt.voice, "matthew")

    service = AWSNovaSonicLLMService(
        access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
        secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        region=nova_region,
        model="amazon.nova-2-sonic-v1:0",
        voice_id=nova_voice,
        system_instruction=prompt.instructions,
        params=Params(
            endpointing_sensitivity="MEDIUM",  # Options: LOW, MEDIUM, HIGH (must be uppercase)
        ),
    )

    return service


def create_twilio_transport(
    websocket: WebSocket,
    stream_sid: str,
    call_sid: str,
    settings: Settings,
    vad_stop_secs: float = 0.5,
) -> FastAPIWebsocketTransport:
    """Create a Twilio-compatible WebSocket transport.

    Args:
        websocket: FastAPI WebSocket connection
        stream_sid: Twilio stream SID
        call_sid: Twilio call SID
        settings: Application settings
        vad_stop_secs: VAD silence threshold

    Returns:
        Configured FastAPI WebSocket transport with Twilio serializer
    """
    # Create Twilio frame serializer for G.711 μ-law audio
    # Disable auto_hang_up since we handle call termination through our own escalation flow
    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
    )

    # Configure transport - disable local VAD since OpenAI Realtime has server-side VAD
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=8000,  # Twilio uses 8kHz
            audio_out_sample_rate=8000,
            vad_enabled=False,  # OpenAI Realtime uses server-side VAD
            vad_audio_passthrough=True,
            serializer=serializer,
        ),
    )

    return transport


async def create_voice_pipeline(
    websocket: WebSocket,
    stream_sid: str,
    call_sid: str,
    settings: Settings,
    config: PipelineConfig,
) -> PipelineComponents:
    """Create a complete voice AI pipeline.

    Creates and configures all components needed for a voice conversation:
    - Twilio WebSocket transport
    - Voice AI service (OpenAI Realtime or Nova Sonic)
    - Escalation processor for keyword detection
    - Pipeline and runner

    Args:
        websocket: FastAPI WebSocket connection
        stream_sid: Twilio stream SID
        call_sid: Twilio call SID
        settings: Application settings
        config: Pipeline configuration

    Returns:
        PipelineComponents with all configured components
    """
    logger.info(
        "Creating voice pipeline",
        extra={
            "provider": config.provider,
            "stream_sid": stream_sid,
            "call_sid": call_sid,
        },
    )

    # Create transport
    transport = create_twilio_transport(
        websocket=websocket,
        stream_sid=stream_sid,
        call_sid=call_sid,
        settings=settings,
        vad_stop_secs=config.vad_stop_secs,
    )

    # Create voice AI service based on provider
    context_aggregator = None
    if config.provider == "nova":
        llm_service = _create_nova_sonic_service(settings, config.prompt)

        # Nova Sonic requires LLMContext and aggregator for LLMRunFrame handling
        # Initialize context with system instruction and initial user message
        context = LLMContext(
            messages=[
                {"role": "system", "content": config.prompt.instructions},
                {"role": "user", "content": "Hello!"},
            ]
        )
        context_aggregator = LLMContextAggregatorPair(context)

        # Nova Sonic pipeline with context aggregators
        # The context aggregators process LLMRunFrame and manage conversation state
        pipeline_processors = [
            transport.input(),
            context_aggregator.user(),
            llm_service,
            transport.output(),
            context_aggregator.assistant(),
        ]
    else:
        # OpenAI Realtime - also multimodal with native audio
        llm_service = _create_openai_realtime_service(settings, config.prompt)
        pipeline_processors = [
            transport.input(),
            llm_service,
            transport.output(),
        ]

    # Create escalation processor if callback provided
    escalation_processor = None
    if config.on_escalation:
        escalation_processor = EscalationProcessor(
            session=config.session,
            on_escalation=config.on_escalation,
        )
        # Insert escalation processor BEFORE LLM to capture upstream transcription frames
        # OpenAI Realtime pushes TranscriptionFrame upstream, so we need to be before LLM
        # Pipeline: transport.input() -> escalation_processor -> llm -> transport.output()
        if config.provider == "nova":
            # Nova: insert after user aggregator (index 1), before LLM (index 2)
            # Pipeline: input -> user_agg -> escalation -> llm -> output -> assistant_agg
            pipeline_processors.insert(2, escalation_processor)
        else:
            # OpenAI: insert after input (index 0), before LLM (index 1)
            # Pipeline: input -> escalation -> llm -> output
            pipeline_processors.insert(1, escalation_processor)

    # Build pipeline
    pipeline = Pipeline(pipeline_processors)  # type: ignore[arg-type]

    # Create task with parameters
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    # Create runner
    runner = PipelineRunner()

    # Set up initial greeting on connection
    @transport.event_handler("on_client_connected")
    async def _on_connected(  # pyright: ignore[reportUnusedFunction]
        transport_instance: Any, client: Any
    ) -> None:
        logger.info(
            "Client connected, triggering initial greeting",
            extra={"provider": config.provider},
        )
        # Trigger the AI to speak first - method depends on provider
        if config.provider == "nova":
            # Nova 2 Sonic: The context already has system instruction and initial "Hello!"
            # Just send LLMRunFrame to trigger the LLM to generate a response
            await task.queue_frames([LLMRunFrame()])
        else:
            # OpenAI Realtime can be triggered with an empty TTS frame
            await task.queue_frames([TTSSpeakFrame(text="")])

    return PipelineComponents(
        transport=transport,
        pipeline=pipeline,
        task=task,
        runner=runner,
        escalation_processor=escalation_processor,
        llm_service=llm_service,
    )


async def run_pipeline(components: PipelineComponents) -> None:
    """Run the voice AI pipeline.

    Args:
        components: Pipeline components from create_voice_pipeline
    """
    logger.info("Starting pipeline runner")
    try:
        await components.runner.run(components.task)
    except Exception as e:
        logger.error("Pipeline error", extra={"error": str(e)}, exc_info=True)
        raise
    finally:
        logger.info("Pipeline runner completed")


async def stop_pipeline(components: PipelineComponents, send_goodbye: bool = True) -> None:
    """Stop the voice AI pipeline gracefully.

    Args:
        components: Pipeline components to stop
        send_goodbye: Whether to send a goodbye message before stopping
    """
    logger.info("Stopping pipeline")

    if send_goodbye:
        try:
            await components.task.queue_frames(
                [
                    TTSSpeakFrame(text="Goodbye."),
                    EndFrame(),
                ]
            )
        except Exception as e:
            logger.warning("Failed to send goodbye", extra={"error": str(e)})

    try:
        await components.task.cancel()
    except Exception as e:
        logger.warning("Error cancelling task", extra={"error": str(e)})
