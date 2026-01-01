"""AWS client factory and utilities."""

import logging
from typing import Any

import boto3
from botocore.config import Config

from shared.config import Settings

logger = logging.getLogger(__name__)


def create_dynamodb_client(settings: Settings) -> Any:
    """Create a DynamoDB client with appropriate configuration."""
    config = Config(
        region_name=settings.aws_region,
        retries={"max_attempts": 3, "mode": "adaptive"},
    )

    client_kwargs: dict[str, Any] = {"config": config}

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    if settings.use_local_dynamodb and settings.dynamodb_endpoint_url:
        client_kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
        logger.info("Using local DynamoDB", extra={"endpoint": settings.dynamodb_endpoint_url})

    return boto3.client("dynamodb", **client_kwargs)


def create_dynamodb_resource(settings: Settings) -> Any:
    """Create a DynamoDB resource with appropriate configuration."""
    config = Config(
        region_name=settings.aws_region,
        retries={"max_attempts": 3, "mode": "adaptive"},
        connect_timeout=5,  # 5 second connection timeout
        read_timeout=10,  # 10 second read timeout
    )

    resource_kwargs: dict[str, Any] = {"config": config}

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        resource_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        resource_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    if settings.use_local_dynamodb and settings.dynamodb_endpoint_url:
        resource_kwargs["endpoint_url"] = settings.dynamodb_endpoint_url

    return boto3.resource("dynamodb", **resource_kwargs)


def create_bedrock_agent_runtime_client(settings: Settings) -> Any:
    """Create a Bedrock Agent Runtime client for Knowledge Base queries.

    This client is used for:
    - retrieve_and_generate() - Semantic search with LLM synthesis
    - retrieve() - Raw semantic search without LLM
    """
    config = Config(
        region_name=settings.kb_region,
        retries={"max_attempts": 5, "mode": "adaptive"},  # Higher retries for KB queries
        connect_timeout=10,  # Longer timeout for Bedrock
        read_timeout=30,  # Longer read timeout for LLM operations
    )

    client_kwargs: dict[str, Any] = {"config": config}

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    logger.info("Creating Bedrock Agent Runtime client", extra={"region": settings.kb_region})
    return boto3.client("bedrock-agent-runtime", **client_kwargs)


def create_bedrock_agent_client(settings: Settings) -> Any:
    """Create a Bedrock Agent client for Knowledge Base management.

    This client is used for:
    - start_ingestion_job() - Trigger KB data source sync
    - get_ingestion_job() - Check ingestion job status
    """
    config = Config(
        region_name=settings.kb_region,
        retries={"max_attempts": 5, "mode": "adaptive"},
        connect_timeout=10,
        read_timeout=30,
    )

    client_kwargs: dict[str, Any] = {"config": config}

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    logger.info("Creating Bedrock Agent client", extra={"region": settings.kb_region})
    return boto3.client("bedrock-agent", **client_kwargs)


def create_s3_client(settings: Settings) -> Any:
    """Create an S3 client for Knowledge Base document uploads.

    Used for uploading transformed Airtable documents to S3,
    which are then ingested into Bedrock Knowledge Base.
    """
    config = Config(
        region_name=settings.aws_region,  # Use main AWS region for S3
        retries={"max_attempts": 3, "mode": "adaptive"},
        connect_timeout=5,
        read_timeout=10,
    )

    client_kwargs: dict[str, Any] = {"config": config}

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
        client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    logger.info("Creating S3 client", extra={"region": settings.aws_region})
    return boto3.client("s3", **client_kwargs)
