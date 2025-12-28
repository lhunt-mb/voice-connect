"""Structured JSON logging configuration."""

import logging
import sys
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger import jsonlogger

# Context variables for correlation IDs
call_sid_ctx: ContextVar[str | None] = ContextVar("call_sid", default=None)
stream_sid_ctx: ContextVar[str | None] = ContextVar("stream_sid", default=None)
conversation_id_ctx: ContextVar[str | None] = ContextVar("conversation_id", default=None)
handover_id_ctx: ContextVar[str | None] = ContextVar("handover_id", default=None)


class CorrelationIdFilter(logging.Filter):
    """Add correlation IDs to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation IDs from context to log record."""
        record.call_sid = call_sid_ctx.get()  # type: ignore[attr-defined]
        record.stream_sid = stream_sid_ctx.get()  # type: ignore[attr-defined]
        record.conversation_id = conversation_id_ctx.get()  # type: ignore[attr-defined]
        record.handover_id = handover_id_ctx.get()  # type: ignore[attr-defined]
        return True


class CustomJsonFormatter(jsonlogger.JsonFormatter):  # type: ignore[misc]
    """Custom JSON formatter with correlation IDs."""

    def add_fields(  # type: ignore[override]
        self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]
    ) -> None:
        """Add custom fields to the log record."""
        super().add_fields(log_record, record, message_dict)

        # Add correlation IDs if present
        if hasattr(record, "call_sid") and record.call_sid:  # type: ignore[attr-defined]
            log_record["call_sid"] = record.call_sid  # type: ignore[attr-defined]
        if hasattr(record, "stream_sid") and record.stream_sid:  # type: ignore[attr-defined]
            log_record["stream_sid"] = record.stream_sid  # type: ignore[attr-defined]
        if hasattr(record, "conversation_id") and record.conversation_id:  # type: ignore[attr-defined]
            log_record["conversation_id"] = record.conversation_id  # type: ignore[attr-defined]
        if hasattr(record, "handover_id") and record.handover_id:  # type: ignore[attr-defined]
            log_record["handover_id"] = record.handover_id  # type: ignore[attr-defined]

        # Ensure level is always present
        log_record["level"] = record.levelname
        log_record["logger"] = record.name


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())

    # Reduce noise from third-party libraries
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
