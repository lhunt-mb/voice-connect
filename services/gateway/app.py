"""FastAPI application for AI Voice Gateway."""

import asyncio
import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.types import ExceptionHandler
from twilio.twiml.voice_response import Connect, Dial, Number, VoiceResponse

from services.gateway.session_manager import SessionManager
from services.gateway.stream_handler import StreamHandler
from services.orchestrator.dynamo_repository import DynamoRepository
from services.orchestrator.ingestion_orchestrator import IngestionOrchestrator
from services.orchestrator.kb_repository import KnowledgeBaseRepository
from services.orchestrator.nova_sonic import NovaClient
from services.orchestrator.openai_realtime import OpenAIRealtimeClient
from services.orchestrator.orchestrator import Orchestrator
from services.orchestrator.prompts import QLD_INTAKE_PROMPT
from services.orchestrator.tool_executor import ToolExecutor
from services.orchestrator.voice_client_base import VoiceClientBase
from shared.config import get_settings
from shared.langfuse_tracing import flush_langfuse, init_langfuse
from shared.logging import setup_logging

# Initialize settings and logging
settings = get_settings()
setup_logging(settings.log_level)

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

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

    # Initialize Langfuse for observability
    init_langfuse(settings)

    await initialize_dynamodb()
    yield

    # Flush Langfuse events before shutdown
    flush_langfuse()
    logger.info("Shutting down AI Voice Gateway service")


# Initialize FastAPI app with lifespan
app = FastAPI(title="AI Voice Gateway", version="0.1.0", lifespan=lifespan)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, cast(ExceptionHandler, _rate_limit_exceeded_handler))

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
    stream = connect.stream(url=stream_url)
    # Pass caller phone number as custom parameter to the WebSocket stream
    if caller_phone:
        stream.parameter(name="From", value=caller_phone)  # type: ignore[union-attr]
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


# Admin endpoints for Airtable ingestion


class IngestionRequest(BaseModel):
    """Request model for single table ingestion."""

    table_id: str


@app.post("/admin/ingest-airtable")
@limiter.limit("10/hour")  # type: ignore[misc]
async def ingest_airtable(
    request: Request,
    ingestion_request: IngestionRequest,
    x_admin_api_key: str = Header(..., alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """Trigger Airtable ingestion for a single table (admin only).

    Requires admin API key in X-Admin-API-Key header.
    Rate limited to 10 requests per hour per IP.

    Example:
        POST /admin/ingest-airtable
        X-Admin-API-Key: <key>
        {"table_id": "tblHRgg8ntGwJzbg0"}

    Valid table IDs:
    - tblHRgg8ntGwJzbg0 (Products)
    - tblUwjFzHhcCae0EE (Needs)
    - tbl0Qp8t6CDe7SLzd (Service Providers)
    - tblpiWbvxAlMJsnTf (Guardrails)
    """
    # Validate API key
    if not settings.admin_api_key:
        raise HTTPException(status_code=500, detail="Admin API key not configured")

    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(x_admin_api_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    logger.info(
        "Admin ingestion request received",
        extra={"table_id": ingestion_request.table_id},
    )

    # Run ingestion for single table
    orchestrator = IngestionOrchestrator(settings)
    result = await orchestrator.ingest_table(ingestion_request.table_id)

    # Convert dataclass to dict
    return {
        "job_id": result.job_id,
        "status": result.status,
        "table_id": result.table_id,
        "table_type": result.table_type,
        "records_fetched": result.records_fetched,
        "documents_created": result.documents_created,
        "s3_objects_uploaded": result.s3_objects_uploaded,
        "s3_objects_deleted": result.s3_objects_deleted,
        "ingestion_job_id": result.ingestion_job_id,
        "elapsed_seconds": result.elapsed_seconds,
        "errors": result.errors,
    }


@app.post("/admin/ingest-all-tables")
@limiter.limit("5/hour")  # type: ignore[misc]
async def ingest_all_tables(
    request: Request,
    x_admin_api_key: str = Header(..., alias="X-Admin-API-Key"),
) -> dict[str, Any]:
    """Trigger Airtable ingestion for all 4 tables (admin only).

    Ingests Products, Needs, Service Providers, and Guardrails in sequence.
    Requires admin API key in X-Admin-API-Key header.
    Rate limited to 5 requests per hour per IP.

    Example:
        POST /admin/ingest-all-tables
        X-Admin-API-Key: <key>
    """
    # Validate API key
    if not settings.admin_api_key:
        raise HTTPException(status_code=500, detail="Admin API key not configured")

    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(x_admin_api_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    logger.info("Admin request to ingest all tables")

    # Run ingestion for all tables
    orchestrator = IngestionOrchestrator(settings)
    results = await orchestrator.ingest_all_tables()

    # Calculate summary
    successful = sum(1 for r in results if r.status == "completed")
    failed = sum(1 for r in results if r.status == "failed")
    total_records = sum(r.records_fetched for r in results)

    # Convert results to dicts
    results_dicts = [
        {
            "job_id": r.job_id,
            "status": r.status,
            "table_id": r.table_id,
            "table_type": r.table_type,
            "records_fetched": r.records_fetched,
            "documents_created": r.documents_created,
            "s3_objects_uploaded": r.s3_objects_uploaded,
            "s3_objects_deleted": r.s3_objects_deleted,
            "ingestion_job_id": r.ingestion_job_id,
            "elapsed_seconds": r.elapsed_seconds,
            "errors": r.errors,
        }
        for r in results
    ]

    return {
        "total_tables": len(results),
        "successful": successful,
        "failed": failed,
        "total_records": total_records,
        "results": results_dicts,
    }


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

        # Initialize tool executor if KB tools are enabled
        tool_executor = None
        if settings.enable_kb_tools:
            logger.info("Initializing Knowledge Base tools", extra={"stream_sid": stream_sid})
            kb_repo = KnowledgeBaseRepository(settings)
            tool_executor = ToolExecutor(kb_repo)

        # Initialize Voice AI client based on configuration
        voice_client: VoiceClientBase
        voice_provider = settings.voice_provider
        if voice_provider == "nova":
            logger.info(
                "Using Amazon Nova 2 Sonic voice provider",
                extra={"stream_sid": stream_sid, "tools_enabled": tool_executor is not None},
            )
            voice_client = NovaClient(settings, prompt=QLD_INTAKE_PROMPT, tool_executor=tool_executor)
        else:
            logger.info(
                "Using OpenAI Realtime voice provider",
                extra={"stream_sid": stream_sid, "tools_enabled": tool_executor is not None},
            )
            voice_client = OpenAIRealtimeClient(settings, prompt=QLD_INTAKE_PROMPT, tool_executor=tool_executor)
            voice_provider = "openai"

        # Create stream handler with Langfuse tracing support
        handler = StreamHandler(websocket, session, voice_client, orchestrator, voice_provider)

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
