"""Lambda handler for Amazon Connect token validation.

This Lambda function is invoked by Amazon Connect contact flows to:
1. Receive a 10-digit DTMF token from contact flow parameters
2. Validate the token format
3. Fetch handover payload from DynamoDB
4. Return contact attributes for screen pop and routing

Expected event structure from Connect:
{
    "Details": {
        "ContactData": {
            "Attributes": {},
            "Channel": "VOICE",
            "ContactId": "...",
            ...
        },
        "Parameters": {
            "token": "1234567890"
        }
    }
}

Return format:
{
    "success": true/false,
    "conversation_id": "...",
    "caller_phone": "...",
    "hubspot_contact_id": "...",
    "hubspot_ticket_id": "...",
    "summary": "...",
    "intent": "...",
    "priority": "...",
    "escalation_reason": "...",
    "error_message": "..." (if failed)
}
"""

import json
import logging
import os
import re
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "HandoverTokens")
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)  # type: ignore[attr-defined]


def validate_token(token: str) -> bool:
    """Validate that token is exactly 10 digits.

    Args:
        token: Token string to validate

    Returns:
        True if valid, False otherwise
    """
    if not token:
        return False

    # Must be exactly 10 digits
    return bool(re.match(r"^\d{10}$", token))


def fetch_handover_payload(token: str) -> dict[str, Any] | None:
    """Fetch handover payload from DynamoDB.

    Args:
        token: Handover token

    Returns:
        Handover payload dict or None if not found
    """
    try:
        response = table.get_item(Key={"token": token})
        item = response.get("Item")

        if not item:
            logger.warning("Token not found in DynamoDB", extra={"token": token})
            return None

        logger.info(
            "Retrieved handover payload", extra={"token": token, "conversation_id": item.get("conversation_id")}
        )
        return item

    except ClientError as e:
        logger.error("DynamoDB error", extra={"error": str(e), "token": token}, exc_info=True)
        return None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for Connect token validation.

    Args:
        event: Lambda event from Amazon Connect
        context: Lambda context

    Returns:
        Dict of contact attributes
    """
    logger.info("Lambda invoked", extra={"event": json.dumps(event)})

    # Extract token from event
    try:
        parameters = event.get("Details", {}).get("Parameters", {})
        token = parameters.get("token", "").strip()

        if not token:
            logger.error("No token provided in event")
            return {
                "success": False,
                "error_message": "No token provided",
                "route_to_queue": "fallback",
            }

    except Exception as e:
        logger.error("Failed to parse event", extra={"error": str(e)}, exc_info=True)
        return {
            "success": False,
            "error_message": "Invalid event format",
            "route_to_queue": "fallback",
        }

    # Validate token format
    if not validate_token(token):
        logger.warning("Invalid token format", extra={"token": token})
        return {
            "success": False,
            "error_message": "Invalid token format",
            "route_to_queue": "fallback",
        }

    # Fetch handover payload
    payload = fetch_handover_payload(token)

    if not payload:
        return {
            "success": False,
            "error_message": "Token not found or expired",
            "route_to_queue": "fallback",
        }

    # Return contact attributes
    return {
        "success": True,
        "conversation_id": payload.get("conversation_id", ""),
        "caller_phone": payload.get("caller_phone", ""),
        "hubspot_contact_id": payload.get("hubspot_contact_id", ""),
        "hubspot_ticket_id": payload.get("hubspot_ticket_id", ""),
        "summary": payload.get("summary", ""),
        "intent": payload.get("intent", ""),
        "priority": payload.get("priority", "medium"),
        "escalation_reason": payload.get("escalation_reason", ""),
        "route_to_queue": "escalation",  # Route to escalation queue
    }
