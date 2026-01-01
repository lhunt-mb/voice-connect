"""S3 uploader for Bedrock Knowledge Base documents."""

import asyncio
import json
import logging
from typing import Any

from shared.aws_clients import create_s3_client
from shared.config import Settings

logger = logging.getLogger(__name__)


class S3Uploader:
    """Upload documents to S3 for Bedrock Knowledge Base ingestion.

    Organizes documents by table type in S3:
    - {prefix}/products/rec123.md
    - {prefix}/needs/rec456.md
    - {prefix}/providers/rec789.md
    - {prefix}/guardrails/rec012.md

    Each document has a corresponding metadata file:
    - {prefix}-metadata/products/rec123.json

    This organization:
    - Helps with debugging and monitoring
    - Allows future filtering by table type
    - Maintains clean separation of concerns
    """

    def __init__(self, settings: Settings):
        """Initialize S3 uploader.

        Args:
            settings: Application settings with S3 configuration
        """
        self.s3_client = create_s3_client(settings)
        self.settings = settings

    async def upload_documents(
        self,
        documents: list[dict[str, Any]],
        table_type: str,
    ) -> int:
        """Upload documents and metadata to S3.

        Args:
            documents: List of transformed documents with content and metadata
            table_type: Table type (products, needs, providers, guardrails)

        Returns:
            Number of S3 objects uploaded (documents + metadata files)

        Raises:
            ValueError: If S3 bucket not configured
        """
        if not self.settings.kb_s3_bucket:
            raise ValueError("S3 bucket not configured for Knowledge Base")

        uploaded = 0
        bucket = self.settings.kb_s3_bucket
        base_prefix = self.settings.kb_s3_prefix

        logger.info(
            "Uploading documents to S3",
            extra={
                "bucket": bucket,
                "table_type": table_type,
                "count": len(documents),
            },
        )

        for doc in documents:
            doc_id = doc["id"]
            content = doc["content"]
            metadata = doc["metadata"]

            # Organize by table type: airtable-docs/products/rec123.md
            s3_key_content = f"{base_prefix}/{table_type}/{doc_id}.md"
            # Store metadata in separate prefix to avoid Bedrock indexing it
            s3_key_metadata = f"{base_prefix}-metadata/{table_type}/{doc_id}.json"

            try:
                # Upload content file (markdown)
                await asyncio.to_thread(
                    self.s3_client.put_object,
                    Bucket=bucket,
                    Key=s3_key_content,
                    Body=content.encode("utf-8"),
                    ContentType="text/markdown",
                )

                # Upload metadata file (JSON)
                await asyncio.to_thread(
                    self.s3_client.put_object,
                    Bucket=bucket,
                    Key=s3_key_metadata,
                    Body=json.dumps(metadata).encode("utf-8"),
                    ContentType="application/json",
                )

                uploaded += 2

                logger.debug(
                    "Uploaded document to S3",
                    extra={"doc_id": doc_id, "table_type": table_type},
                )

            except Exception as e:
                logger.error(
                    "Failed to upload document to S3",
                    extra={
                        "doc_id": doc_id,
                        "table_type": table_type,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                raise

        logger.info(
            "Completed S3 upload",
            extra={
                "bucket": bucket,
                "table_type": table_type,
                "uploaded": uploaded,
            },
        )

        return uploaded

    async def clear_table_type(self, table_type: str) -> int:
        """Delete all documents for a specific table type.

        Used before re-ingesting a table to avoid stale documents.

        Args:
            table_type: Table type to clear (products, needs, providers, guardrails)

        Returns:
            Number of objects deleted

        Raises:
            ValueError: If S3 bucket not configured
        """
        if not self.settings.kb_s3_bucket:
            raise ValueError("S3 bucket not configured for Knowledge Base")

        bucket = self.settings.kb_s3_bucket
        base_prefix = self.settings.kb_s3_prefix
        prefix = f"{base_prefix}/{table_type}/"

        logger.info(
            "Clearing S3 documents",
            extra={"bucket": bucket, "prefix": prefix},
        )

        deleted = 0

        try:
            # List all objects with prefix
            paginator = self.s3_client.get_paginator("list_objects_v2")

            # Process each page of results
            for page in await asyncio.to_thread(lambda: list(paginator.paginate(Bucket=bucket, Prefix=prefix))):
                if "Contents" in page:
                    objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
                    if objects:
                        # Delete objects in batch (up to 1000 per request)
                        await asyncio.to_thread(
                            self.s3_client.delete_objects,
                            Bucket=bucket,
                            Delete={"Objects": objects},
                        )
                        deleted += len(objects)

                        logger.debug(
                            "Deleted S3 objects batch",
                            extra={"count": len(objects)},
                        )

        except Exception as e:
            logger.error(
                "Failed to clear S3 documents",
                extra={
                    "bucket": bucket,
                    "prefix": prefix,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

        logger.info(
            "Completed S3 cleanup",
            extra={"bucket": bucket, "prefix": prefix, "deleted": deleted},
        )

        return deleted
