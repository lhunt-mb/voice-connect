"""Async client for Airtable API with rate limiting and retry logic."""

import asyncio
import logging
from collections.abc import AsyncGenerator

import httpx
from pyairtable import Api
from pyairtable.api.types import RecordDict
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared.config import Settings

logger = logging.getLogger(__name__)


class AirtableClient:
    """Async client for Airtable API with pagination and rate limiting.

    Features:
    - Automatic pagination through all records
    - Rate limiting (5 requests/second Airtable limit)
    - Exponential backoff retry on errors
    - Async/await support using asyncio.to_thread
    """

    def __init__(self, settings: Settings):
        """Initialize Airtable client.

        Args:
            settings: Application settings with Airtable configuration
        """
        if not settings.airtable_api_token:
            raise ValueError("Airtable API token not configured")

        self.api = Api(settings.airtable_api_token)
        self.rate_limiter = asyncio.Semaphore(5)  # 5 concurrent requests max

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, Exception)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
    )
    async def fetch_all_records(
        self,
        base_id: str,
        table_name: str,
    ) -> AsyncGenerator[RecordDict, None]:
        """Fetch all records from an Airtable table with pagination.

        Args:
            base_id: Airtable base ID (e.g., 'appnM3j6FvK8goI8i')
            table_name: Table ID or name (e.g., 'tblHRgg8ntGwJzbg0')

        Yields:
            Record dictionaries with 'id', 'fields', 'createdTime'

        Raises:
            ValueError: If base_id or table_name not provided
            httpx.RequestError: On network errors (retried automatically)
        """
        if not base_id or not table_name:
            raise ValueError("base_id and table_name are required")

        logger.info(
            "Fetching records from Airtable",
            extra={"base_id": base_id, "table_name": table_name},
        )

        try:
            # Get table handle
            table = self.api.table(base_id, table_name)

            # Use rate limiter to respect Airtable's 5 req/sec limit
            async with self.rate_limiter:
                # Fetch all records with automatic pagination
                # pyairtable's all() method handles pagination internally
                records = await asyncio.to_thread(table.all)

                logger.info(
                    "Fetched records from Airtable",
                    extra={
                        "base_id": base_id,
                        "table_name": table_name,
                        "count": len(records),
                    },
                )

                # Yield records one at a time
                for record in records:
                    yield record

        except Exception as e:
            logger.error(
                "Failed to fetch Airtable records",
                extra={
                    "base_id": base_id,
                    "table_name": table_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
