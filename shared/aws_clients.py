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
