"""Orchestrator for Airtable → S3 → Bedrock KB ingestion pipeline."""

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field

from services.orchestrator.airtable_client import AirtableClient
from services.orchestrator.document_transformer import DocumentTransformer
from services.orchestrator.s3_uploader import S3Uploader
from shared.aws_clients import create_bedrock_agent_client
from shared.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result from an Airtable ingestion job."""

    job_id: str
    status: str  # "completed" or "failed"
    table_id: str | None = None
    table_type: str | None = None
    records_fetched: int = 0
    documents_created: int = 0
    s3_objects_uploaded: int = 0
    s3_objects_deleted: int = 0
    ingestion_job_id: str | None = None
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class IngestionOrchestrator:
    """Orchestrate Airtable → S3 → Bedrock KB ingestion pipeline.

    Pipeline steps:
    1. Clear existing documents for table type from S3
    2. Fetch records from Airtable with pagination
    3. Transform records using table-specific templates
    4. Upload documents and metadata to S3
    5. Trigger Bedrock Knowledge Base ingestion job

    Supports 4 Airtable tables:
    - Products (tblHRgg8ntGwJzbg0)
    - Needs (tblUwjFzHhcCae0EE)
    - Service Providers (tbl0Qp8t6CDe7SLzd)
    - Guardrails (tblpiWbvxAlMJsnTf)
    """

    # Map Airtable table IDs to friendly names
    TABLE_ID_MAP = {
        "tblHRgg8ntGwJzbg0": "products",
        "tblUwjFzHhcCae0EE": "needs",
        "tbl0Qp8t6CDe7SLzd": "providers",
        "tblpiWbvxAlMJsnTf": "guardrails",
    }

    def __init__(self, settings: Settings):
        """Initialize ingestion orchestrator.

        Args:
            settings: Application settings
        """
        self.airtable_client = AirtableClient(settings)
        self.transformer = DocumentTransformer()
        self.s3_uploader = S3Uploader(settings)
        self.bedrock_agent = create_bedrock_agent_client(settings)
        self.settings = settings

    async def ingest_table(
        self,
        table_id: str,
    ) -> IngestionResult:
        """Run full ingestion pipeline for a specific Airtable table.

        Args:
            table_id: Airtable table ID (e.g., 'tblHRgg8ntGwJzbg0')

        Returns:
            IngestionResult with status and metrics
        """
        job_id = str(uuid.uuid4())
        start_time = time.time()

        # Get table type from mapping
        table_type = self.TABLE_ID_MAP.get(table_id)
        if not table_type:
            logger.error("Unknown table ID", extra={"table_id": table_id})
            return IngestionResult(
                job_id=job_id,
                status="failed",
                table_id=table_id,
                elapsed_seconds=0,
                errors=[f"Unknown table ID: {table_id}. Valid IDs: {list(self.TABLE_ID_MAP.keys())}"],
            )

        logger.info(
            "Starting ingestion job",
            extra={
                "job_id": job_id,
                "table_id": table_id,
                "table_type": table_type,
            },
        )

        try:
            # Step 1: Clear existing documents for this table type
            logger.info(f"Step 1/5: Clearing existing {table_type} documents from S3")
            deleted = await self.s3_uploader.clear_table_type(table_type)
            logger.info(f"Deleted {deleted} existing objects")

            # Step 2: Fetch from Airtable
            logger.info(f"Step 2/5: Fetching records from Airtable table {table_id}")
            records = []
            async for record in self.airtable_client.fetch_all_records(
                self.settings.airtable_base_id,  # type: ignore[arg-type]
                table_id,
            ):
                records.append(record)
            logger.info(f"Fetched {len(records)} records")

            # Step 3: Transform to documents with table-specific templates
            logger.info(f"Step 3/5: Transforming records using {table_type} template")
            documents = [self.transformer.transform_record(r, table_id) for r in records]
            logger.info(f"Created {len(documents)} documents")

            # Step 4: Upload to S3 (organized by table type)
            logger.info(f"Step 4/5: Uploading {len(documents)} documents to S3")
            uploaded = await self.s3_uploader.upload_documents(documents, table_type)
            logger.info(f"Uploaded {uploaded} S3 objects")

            # Step 5: Trigger Bedrock ingestion with idempotency token
            logger.info("Step 5/5: Triggering Bedrock Knowledge Base ingestion job")

            # Generate deterministic idempotency token (5-minute window)
            token_input = f"{table_id}-{int(time.time() // 300)}"
            client_token = hashlib.sha256(token_input.encode()).hexdigest()[:64]

            response = await asyncio.to_thread(
                self.bedrock_agent.start_ingestion_job,
                knowledgeBaseId=self.settings.kb_knowledge_base_id,
                dataSourceId=self.settings.kb_data_source_id,
                clientToken=client_token,
            )

            ingestion_job_id = response["ingestionJob"]["ingestionJobId"]
            logger.info(f"Bedrock ingestion job started: {ingestion_job_id}", extra={"client_token": client_token})

            elapsed = time.time() - start_time

            result = IngestionResult(
                job_id=job_id,
                status="completed",
                table_id=table_id,
                table_type=table_type,
                records_fetched=len(records),
                documents_created=len(documents),
                s3_objects_uploaded=uploaded,
                s3_objects_deleted=deleted,
                ingestion_job_id=ingestion_job_id,
                elapsed_seconds=elapsed,
            )

            logger.info(
                "Ingestion job completed successfully",
                extra={
                    "job_id": job_id,
                    "table_type": table_type,
                    "elapsed_seconds": elapsed,
                    "records": len(records),
                },
            )

            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "Ingestion job failed",
                extra={
                    "job_id": job_id,
                    "table_id": table_id,
                    "table_type": table_type,
                    "error": str(e),
                },
                exc_info=True,
            )

            return IngestionResult(
                job_id=job_id,
                status="failed",
                table_id=table_id,
                table_type=table_type,
                elapsed_seconds=elapsed,
                errors=[str(e)],
            )

    async def ingest_all_tables(self) -> list[IngestionResult]:
        """Ingest all 4 Airtable tables in sequence.

        Returns:
            List of IngestionResult objects, one per table
        """
        logger.info("Starting ingestion for all tables")

        results = []
        for table_id in self.TABLE_ID_MAP:
            table_type = self.TABLE_ID_MAP[table_id]
            logger.info(f"Starting ingestion for table {table_id} ({table_type})")

            result = await self.ingest_table(table_id)
            results.append(result)

            if result.status == "failed":
                logger.error(
                    f"Failed to ingest {table_id}, continuing to next table",
                    extra={"errors": result.errors},
                )
            else:
                logger.info(
                    f"Successfully ingested {table_id}",
                    extra={
                        "records": result.records_fetched,
                        "elapsed": result.elapsed_seconds,
                    },
                )

        # Log summary
        successful = sum(1 for r in results if r.status == "completed")
        failed = sum(1 for r in results if r.status == "failed")
        total_records = sum(r.records_fetched for r in results)

        logger.info(
            "Completed ingestion for all tables",
            extra={
                "total_tables": len(results),
                "successful": successful,
                "failed": failed,
                "total_records": total_records,
            },
        )

        return results
