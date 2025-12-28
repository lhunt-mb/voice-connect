"""FastAPI application for AI Voice Gateway."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import Connect, Dial, Number, VoiceResponse

from services.gateway.session_manager import SessionManager
from services.gateway.stream_handler import StreamHandler
from services.orchestrator.dynamo_repository import DynamoRepository
from services.orchestrator.nova_sonic import NovaClient
from services.orchestrator.openai_realtime import OpenAIRealtimeClient
from services.orchestrator.orchestrator import Orchestrator
from services.orchestrator.voice_client_base import VoiceClientBase
from shared.config import get_settings
from shared.logging import setup_logging

# Initialize settings and logging
settings = get_settings()
setup_logging(settings.log_level)

logger = logging.getLogger(__name__)

# Initialize DynamoDB repository (but don't create table yet)
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
                wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s, 8s, 16s
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
    logger.info("Starting AI Voice Gateway service")
    await initialize_dynamodb()
    yield
    logger.info("Shutting down AI Voice Gateway service")


# Initialize FastAPI app with lifespan
app = FastAPI(title="AI Voice Gateway", version="0.1.0", lifespan=lifespan)

# Global instances
session_manager = SessionManager()
orchestrator = Orchestrator(settings)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.api_route("/twilio/voice", methods=["GET", "POST"])
async def twilio_voice_webhook(request: Request) -> HTMLResponse:
    """Twilio voice webhook endpoint.

    Returns TwiML to initiate bidirectional Media Stream.

    Expected Twilio request parameters:
    - CallSid: Unique call identifier
    - From: Caller phone number
    - To: Called phone number
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    caller_phone = form_data.get("From")

    logger.info(
        "Incoming call",
        extra={"call_sid": call_sid, "caller_phone": caller_phone},
    )

    # Build TwiML using Twilio library for proper bidirectional streaming
    response = VoiceResponse()

    # Connect to WebSocket stream for bidirectional audio
    # OpenAI will handle the greeting
    stream_url = f"wss://{settings.public_host}/twilio/stream"

    # Set action URL to be called when stream ends
    # This allows us to handle escalation after the stream closes
    action_url = f"https://{settings.public_host}/twilio/stream-ended"

    connect = Connect(action=action_url, method="POST")
    connect.stream(url=stream_url)
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.api_route("/twilio/stream-ended", methods=["GET", "POST"])
async def twilio_stream_ended(request: Request) -> HTMLResponse:
    """Handle the callback when Media Stream ends.

    This checks if the stream ended due to escalation and routes accordingly.
    """
    form_data = await request.form()

    # Log all parameters for troubleshooting
    all_params = dict(form_data)
    logger.info(
        "Media Stream ended - all parameters",
        extra={"params": all_params},
    )

    call_sid = form_data.get("CallSid", "unknown")
    if not isinstance(call_sid, str):
        call_sid = "unknown"

    logger.info(
        "Media Stream ended",
        extra={"call_sid": call_sid},
    )

    # Check if there's an active escalation for this call
    session = session_manager.get_session_by_call_sid(call_sid)

    if session and session.metadata.get("handover_token"):
        # There's an escalation - redirect to escalation handler
        token = session.metadata["handover_token"]
        logger.info(
            "Escalation active, redirecting to agent",
            extra={"call_sid": call_sid, "token": token},
        )

        # Clean up the session now that we've retrieved the token
        if session.stream_sid:
            session_manager.remove_session(session.stream_sid)

        # Build TwiML for escalation
        response = VoiceResponse()

        # Play brief hold message
        response.say(
            "Please hold while we connect you to an agent.",
            voice="Polly.Joanna",
        )

        # Dial Amazon Connect with DTMF token
        # Twilio will automatically handle ringback/hold during the dial attempt
        dial = Dial(timeout=30, action=f"https://{settings.public_host}/twilio/escalate-status")
        number = Number(settings.connect_phone_number, send_digits=f"wwww{token}#")
        dial.append(number)
        response.append(dial)

        # If dial fails or completes, thank the caller
        response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
        response.hangup()

        return HTMLResponse(content=str(response), media_type="application/xml")
    else:
        # Normal stream end - just hang up
        logger.info("Stream ended normally, hanging up", extra={"call_sid": call_sid})

        # Clean up the session
        if session and session.stream_sid:
            session_manager.remove_session(session.stream_sid)

        response = VoiceResponse()
        response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
        response.hangup()
        return HTMLResponse(content=str(response), media_type="application/xml")


@app.api_route("/twilio/escalate", methods=["GET", "POST"])
async def twilio_escalate_webhook(request: Request) -> HTMLResponse:
    """Twilio escalation webhook endpoint.

    Returns TwiML to play hold music and dial Amazon Connect with DTMF.
    This endpoint is called when redirecting an active call during escalation.

    Expected query parameters:
    - token: The handover token to send via DTMF
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")

    # Get token from query string
    token = request.query_params.get("token", "")

    logger.info(
        "Escalation webhook called",
        extra={"call_sid": call_sid, "token": token},
    )

    # Build TwiML for escalation
    response = VoiceResponse()

    # Play hold message
    response.say(
        "Please hold while we connect you to an agent. This may take a moment.",
        voice="Polly.Joanna",
    )

    # Play hold music while connecting
    # Note: You can replace this with a URL to custom hold music
    response.play(url="http://com.twilio.sounds.music.s3.amazonaws.com/MARKOVICHAMP-Borghestral.mp3", loop=5)

    # Dial Amazon Connect with DTMF token
    # The 'w' characters add pauses (0.5s each) before sending digits
    dial = Dial(timeout=30, action=f"https://{settings.public_host}/twilio/escalate-status")
    number = Number(settings.connect_phone_number, send_digits=f"wwww{token}#")
    dial.append(number)
    response.append(dial)

    # If dial fails or completes, thank the caller
    response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
    response.hangup()

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.api_route("/twilio/escalate-status", methods=["GET", "POST"])
async def twilio_escalate_status(request: Request) -> HTMLResponse:
    """Handle the status callback after attempting to dial Connect.

    This is called by Twilio after the Dial attempt completes.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    dial_call_status = form_data.get("DialCallStatus", "unknown")

    logger.info(
        "Escalation dial status",
        extra={"call_sid": call_sid, "dial_call_status": dial_call_status},
    )

    # Build TwiML response based on dial status
    response = VoiceResponse()

    if dial_call_status in ["completed", "answered"]:
        # Call was successful, just hang up (agent is handling it)
        response.hangup()
    else:
        # Call failed
        response.say(
            "We're sorry, but we couldn't connect you to an agent at this time. Please try again later.",
            voice="Polly.Joanna",
        )
        response.hangup()

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/twilio/stream")
async def twilio_stream_websocket(websocket: WebSocket) -> None:
    """Twilio Media Stream WebSocket endpoint.

    Handles bidirectional audio streaming between Twilio and OpenAI.

    Twilio Media Streams Protocol:
    - Receives: start, media, stop events
    - Sends: media events with audio payload
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    session = None
    stream_sid = None

    try:
        # Wait for start event to get stream details
        data = await websocket.receive_text()
        import json

        start_message = json.loads(data)

        if start_message.get("event") == "connected":
            # Twilio sends 'connected' first, wait for 'start'
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

        # Initialize Voice AI client based on configuration
        voice_client: VoiceClientBase
        if settings.voice_provider == "nova":
            logger.info("Using Amazon Nova 2 Sonic voice provider")
            voice_client = NovaClient(settings)
        else:
            logger.info("Using OpenAI Realtime voice provider")
            voice_client = OpenAIRealtimeClient(settings)

        # Create stream handler
        handler = StreamHandler(websocket, session, voice_client, orchestrator)

        # Handle the stream
        await handler.handle_stream()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", extra={"stream_sid": stream_sid})
    except Exception as e:
        logger.error("WebSocket error", extra={"error": str(e), "stream_sid": stream_sid}, exc_info=True)
    finally:
        # Don't remove session immediately - the action URL needs it!
        # The action URL (/twilio/stream-ended) will handle cleanup
        # after it's done processing the escalation
        logger.info("WebSocket closed, keeping session for action URL", extra={"stream_sid": stream_sid})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
