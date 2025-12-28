"""DynamoDB repository for handover tokens."""

import logging
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from shared.aws_clients import create_dynamodb_resource
from shared.config import Settings
from shared.types import HandoverPayload

logger = logging.getLogger(__name__)


class DynamoRepository:
    """Repository for managing handover tokens in DynamoDB."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the DynamoDB repository."""
        self.settings = settings
        self.dynamodb = create_dynamodb_resource(settings)
        self.table = self.dynamodb.Table(settings.dynamodb_table_name)

    def create_table_if_not_exists(self) -> None:
        """Create the HandoverTokens table if it doesn't exist (for local dev)."""
        if not self.settings.use_local_dynamodb:
            return

        try:
            # Try to describe the table using the low-level client (faster than load())
            client = self.dynamodb.meta.client
            client.describe_table(TableName=self.settings.dynamodb_table_name)
            logger.info("DynamoDB table exists", extra={"table": self.settings.dynamodb_table_name})
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.info("Creating DynamoDB table", extra={"table": self.settings.dynamodb_table_name})
                client = self.dynamodb.meta.client
                client.create_table(
                    TableName=self.settings.dynamodb_table_name,
                    KeySchema=[{"AttributeName": "token", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "token", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST",
                )
                # For local DynamoDB, table is ready immediately after creation
                logger.info("DynamoDB table created", extra={"table": self.settings.dynamodb_table_name})
            else:
                raise

    def put_handover(self, payload: HandoverPayload) -> None:
        """Store a handover payload in DynamoDB."""
        item = {
            "token": payload.token,
            "conversation_id": payload.conversation_id,
            "created_at": payload.created_at.isoformat(),
            "expires_at": int(payload.expires_at.timestamp()),  # TTL attribute (epoch seconds)
            "caller_phone": payload.caller_phone,
            "hubspot_contact_id": payload.hubspot_contact_id,
            "hubspot_ticket_id": payload.hubspot_ticket_id,
            "summary": payload.summary,
            "intent": payload.intent,
            "priority": payload.priority,
            "escalation_reason": payload.escalation_reason.value,
        }

        try:
            self.table.put_item(Item=item)
            logger.info(
                "Stored handover token in DynamoDB",
                extra={"token": payload.token, "conversation_id": payload.conversation_id},
            )
        except ClientError as e:
            logger.error("Failed to store handover token", extra={"error": str(e)}, exc_info=True)
            raise

    def get_handover(self, token: str) -> HandoverPayload | None:
        """Retrieve a handover payload from DynamoDB."""
        try:
            response = self.table.get_item(Key={"token": token})
            item = response.get("Item")

            if not item:
                logger.warning("Handover token not found", extra={"token": token})
                return None

            # Check if expired (TTL check)
            expires_at = datetime.fromtimestamp(item["expires_at"], tz=UTC)
            if datetime.now(UTC) > expires_at:
                logger.warning("Handover token expired", extra={"token": token})
                return None

            payload = HandoverPayload(
                token=item["token"],
                conversation_id=item["conversation_id"],
                created_at=datetime.fromisoformat(item["created_at"]),
                expires_at=expires_at,
                caller_phone=item.get("caller_phone"),
                hubspot_contact_id=item.get("hubspot_contact_id"),
                hubspot_ticket_id=item.get("hubspot_ticket_id"),
                summary=item["summary"],
                intent=item.get("intent"),
                priority=item["priority"],
                escalation_reason=item["escalation_reason"],
            )

            logger.info("Retrieved handover token from DynamoDB", extra={"token": token})
            return payload

        except ClientError as e:
            logger.error("Failed to retrieve handover token", extra={"error": str(e), "token": token}, exc_info=True)
            raise

    def delete_handover(self, token: str) -> None:
        """Delete a handover payload from DynamoDB."""
        try:
            self.table.delete_item(Key={"token": token})
            logger.info("Deleted handover token from DynamoDB", extra={"token": token})
        except ClientError as e:
            logger.error("Failed to delete handover token", extra={"error": str(e), "token": token}, exc_info=True)
            raise
