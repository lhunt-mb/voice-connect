"""FastAPI application for AI Voice Gateway using Pipecat.

This is the Pipecat-based implementation of the voice gateway,
providing a cleaner pipeline architecture for voice AI interactions.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import Connect, Dial, Number, VoiceResponse

from services.gateway.session_manager import SessionManager
from services.orchestrator.dynamo_repository import DynamoRepository
from services.orchestrator.orchestrator import Orchestrator
from services.orchestrator.prompts import get_prompt
from services.pipecat.pipeline_factory import (
    PipelineConfig,
    create_voice_pipeline,
    run_pipeline,
    stop_pipeline,
)
from shared.config import get_settings
from shared.logging import call_sid_ctx, conversation_id_ctx, setup_logging, stream_sid_ctx

# Initialize settings and logging
settings = get_settings()
setup_logging(settings.log_level)

logger = logging.getLogger(__name__)

# Initialize DynamoDB repository
dynamo_repo = DynamoRepository(settings)


async def initialize_dynamodb() -> None:
    """Initialize DynamoDB table with retry logic for local development."""
    if not settings.use_local_dynamodb:
        logger.info("Using production DynamoDB, skipping table creation")
        return

    max_retries = 5
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to create DynamoDB table (attempt {attempt + 1}/{max_retries})")
            await asyncio.to_thread(dynamo_repo.create_table_if_not_exists)
            logger.info("Successfully initialized DynamoDB table")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                logger.warning(
                    f"Failed to initialize DynamoDB (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s",
                    extra={"error": str(e)},
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error("Failed to initialize DynamoDB after all retries", extra={"error": str(e)})
                raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    logger.info("Starting AI Voice Gateway service (Pipecat)")
    await initialize_dynamodb()
    yield
    logger.info("Shutting down AI Voice Gateway service")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="AI Voice Gateway (Pipecat)",
    version="0.2.0",
    description="Voice AI gateway powered by Pipecat framework",
    lifespan=lifespan,
)

# Global instances
session_manager = SessionManager()
orchestrator = Orchestrator(settings)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "framework": "pipecat"}


@app.api_route("/twilio/voice", methods=["GET", "POST"])
async def twilio_voice_webhook(request: Request) -> HTMLResponse:
    """Twilio voice webhook endpoint.

    Returns TwiML to initiate bidirectional Media Stream.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    caller_phone = form_data.get("From")

    logger.info(
        "Incoming call",
        extra={"call_sid": call_sid, "caller_phone": caller_phone},
    )

    response = VoiceResponse()

    stream_url = f"wss://{settings.public_host}/twilio/stream"
    action_url = f"https://{settings.public_host}/twilio/stream-ended"

    connect = Connect(action=action_url, method="POST")
    connect.stream(url=stream_url)
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.api_route("/twilio/stream-ended", methods=["GET", "POST"])
async def twilio_stream_ended(request: Request) -> HTMLResponse:
    """Handle the callback when Media Stream ends.

    Checks if escalation was triggered and routes accordingly.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    if not isinstance(call_sid, str):
        call_sid = "unknown"

    # Debug: log all form data including CallStatus
    call_status = form_data.get("CallStatus", "unknown")
    logger.info(
        "Media Stream ended",
        extra={
            "call_sid": call_sid,
            "call_status": call_status,
            "form_data": dict(form_data.items()),
        },
    )

    session = session_manager.get_session_by_call_sid(call_sid)

    if session and session.metadata.get("handover_token"):
        token = session.metadata["handover_token"]
        logger.info(
            "Escalation active, redirecting to agent",
            extra={"call_sid": call_sid, "token": token},
        )

        if session.stream_sid:
            session_manager.remove_session(session.stream_sid)

        response = VoiceResponse()
        response.say(
            "Please hold while we connect you to an agent.",
            voice="Polly.Joanna",
        )

        # Log the dial attempt details
        logger.info(
            "Dialing Connect",
            extra={
                "connect_number": settings.connect_phone_number,
                "token": token,
                "caller_id": settings.twilio_phone_number,
            },
        )

        dial = Dial(
            timeout=30,
            action=f"https://{settings.public_host}/twilio/escalate-status",
        )
        number = Number(settings.connect_phone_number, send_digits=f"wwww{token}#")
        dial.append(number)
        response.append(dial)

        response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
        response.hangup()

        twiml = str(response)
        logger.info("Returning escalation TwiML", extra={"twiml": twiml})
        return HTMLResponse(content=twiml, media_type="application/xml")
    else:
        logger.info("Stream ended normally, hanging up", extra={"call_sid": call_sid})

        if session and session.stream_sid:
            session_manager.remove_session(session.stream_sid)

        response = VoiceResponse()
        response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
        response.hangup()
        return HTMLResponse(content=str(response), media_type="application/xml")


@app.api_route("/twilio/escalate", methods=["GET", "POST"])
async def twilio_escalate_webhook(request: Request) -> HTMLResponse:
    """Twilio escalation webhook endpoint."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    token = request.query_params.get("token", "")

    logger.info(
        "Escalation webhook called",
        extra={"call_sid": call_sid, "token": token},
    )

    response = VoiceResponse()
    response.say(
        "Please hold while we connect you to an agent. This may take a moment.",
        voice="Polly.Joanna",
    )
    response.play(url="http://com.twilio.sounds.music.s3.amazonaws.com/MARKOVICHAMP-Borghestral.mp3", loop=5)

    dial = Dial(timeout=30, action=f"https://{settings.public_host}/twilio/escalate-status")
    number = Number(settings.connect_phone_number, send_digits=f"wwww{token}#")
    dial.append(number)
    response.append(dial)

    response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
    response.hangup()

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.api_route("/twilio/escalate-status", methods=["GET", "POST"])
async def twilio_escalate_status(request: Request) -> HTMLResponse:
    """Handle the status callback after attempting to dial Connect."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    dial_call_status = form_data.get("DialCallStatus", "unknown")

    logger.info(
        "Escalation dial status",
        extra={"call_sid": call_sid, "dial_call_status": dial_call_status},
    )

    response = VoiceResponse()

    if dial_call_status in ["completed", "answered"]:
        response.hangup()
    else:
        response.say(
            "We're sorry, but we couldn't connect you to an agent at this time. Please try again later.",
            voice="Polly.Joanna",
        )
        response.hangup()

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/twilio/stream")
async def twilio_stream_websocket(websocket: WebSocket) -> None:
    """Twilio Media Stream WebSocket endpoint using Pipecat.

    Handles bidirectional audio streaming between Twilio and voice AI
    using Pipecat's pipeline architecture.
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    session = None
    stream_sid = None
    pipeline_components = None

    try:
        # Wait for start event
        data = await websocket.receive_text()
        start_message = json.loads(data)

        if start_message.get("event") == "connected":
            data = await websocket.receive_text()
            start_message = json.loads(data)

        if start_message.get("event") != "start":
            logger.warning("Expected start event, got: %s", start_message.get("event"))
            return

        # Extract session info
        stream_sid = start_message.get("streamSid")
        start_data = start_message.get("start", {})
        call_sid = start_data.get("callSid")
        caller_phone = start_data.get("customParameters", {}).get("From")

        # Create session
        session = session_manager.create_session(call_sid, stream_sid, caller_phone)

        # Set correlation IDs for logging
        call_sid_ctx.set(call_sid)
        stream_sid_ctx.set(stream_sid)
        conversation_id_ctx.set(session.conversation_id)

        logger.info(
            "Starting Pipecat pipeline",
            extra={
                "provider": settings.voice_provider,
                "stream_sid": stream_sid,
                "call_sid": call_sid,
            },
        )

        # Get prompt configuration
        prompt = get_prompt("default")

        # Create pipeline configuration
        config = PipelineConfig(
            provider=settings.voice_provider,
            prompt=prompt,
            session=session,
            on_escalation=orchestrator.check_and_handle_escalation,
        )

        # Create voice pipeline
        pipeline_components = await create_voice_pipeline(
            websocket=websocket,
            stream_sid=stream_sid,
            call_sid=call_sid,
            settings=settings,
            config=config,
        )

        # Run pipeline
        await run_pipeline(pipeline_components)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", extra={"stream_sid": stream_sid})
    except Exception as e:
        logger.error("WebSocket error", extra={"error": str(e), "stream_sid": stream_sid}, exc_info=True)
    finally:
        # Clean up pipeline if needed
        if pipeline_components:
            try:
                await stop_pipeline(pipeline_components, send_goodbye=False)
            except Exception as e:
                logger.warning("Error stopping pipeline", extra={"error": str(e)})

        logger.info("WebSocket closed, keeping session for action URL", extra={"stream_sid": stream_sid})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
