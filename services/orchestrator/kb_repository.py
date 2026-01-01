"""Repository for Amazon Bedrock Knowledge Base operations."""

import asyncio
import logging
from dataclasses import dataclass

from botocore.exceptions import ClientError

from shared.aws_clients import create_bedrock_agent_runtime_client
from shared.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeBaseResult:
    """Result from a Knowledge Base query."""

    content: str  # Synthesized answer from RetrieveAndGenerate
    sources: list[str]  # Source citations
    score: float = 0.0  # Relevance score


class KnowledgeBaseRepository:
    """Repository for Bedrock Knowledge Base semantic search operations.

    Uses the RetrieveAndGenerate API which:
    1. Performs semantic search across documents
    2. Synthesizes results using an LLM
    3. Returns natural language answers with citations

    This is ideal for voice applications where concise,
    conversational responses are needed.
    """

    def __init__(self, settings: Settings):
        """Initialize the KB repository.

        Args:
            settings: Application settings with KB configuration
        """
        self.settings = settings
        self.bedrock_agent = create_bedrock_agent_runtime_client(settings)

        if not settings.kb_knowledge_base_id:
            logger.warning("Knowledge Base ID not configured - KB queries will fail")

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[KnowledgeBaseResult]:
        """Search Knowledge Base using RetrieveAndGenerate API.

        This performs semantic search and synthesizes a natural language
        answer suitable for voice responses.

        Args:
            query: Search query (with optional context prefix)
            max_results: Maximum number of results (default: 5)

        Returns:
            List of KnowledgeBaseResult objects with synthesized content

        Note:
            Errors are handled gracefully - returns empty list if KB unavailable.
            This prevents voice call drops due to KB issues.
        """
        if not self.settings.kb_knowledge_base_id:
            logger.error("KB not configured", extra={"query": query})
            return []

        try:
            logger.info(
                "Querying Knowledge Base",
                extra={
                    "query": query[:100],  # Log first 100 chars
                    "kb_id": self.settings.kb_knowledge_base_id,
                    "max_results": max_results,
                },
            )

            # Call RetrieveAndGenerate API
            # This combines semantic search + LLM synthesis in one call
            response = await asyncio.to_thread(
                self.bedrock_agent.retrieve_and_generate,
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": self.settings.kb_knowledge_base_id,
                        "modelArn": f"arn:aws:bedrock:{self.settings.kb_region}::foundation-model/amazon.nova-micro-v1:0",  # Fast Amazon model for low latency
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": max_results,
                            }
                        },
                    },
                },
            )

            # Extract synthesized answer
            output = response.get("output", {})
            synthesized_text = output.get("text", "")

            if not synthesized_text:
                logger.warning("Empty response from KB", extra={"query": query[:100]})
                return []

            # Extract source citations
            citations = response.get("citations", [])
            sources = []
            for citation in citations:
                retrieved_refs = citation.get("retrievedReferences", [])
                for ref in retrieved_refs:
                    location = ref.get("location", {})
                    s3_location = location.get("s3Location", {})
                    uri = s3_location.get("uri", "")
                    if uri:
                        sources.append(uri)

            # Remove duplicates while preserving order
            sources = list(dict.fromkeys(sources))

            logger.info(
                "KB query successful",
                extra={
                    "query": query[:100],
                    "response_length": len(synthesized_text),
                    "num_sources": len(sources),
                },
            )

            return [
                KnowledgeBaseResult(
                    content=synthesized_text,
                    sources=sources,
                    score=1.0,  # RetrieveAndGenerate doesn't return scores
                )
            ]

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            logger.error(
                "Bedrock KB query failed",
                extra={
                    "query": query[:100],
                    "error_code": error_code,
                    "error_message": error_message,
                },
                exc_info=True,
            )

            # Return empty list to gracefully degrade
            # Voice call continues without KB results
            return []

        except Exception as e:
            logger.error(
                "Unexpected error querying KB",
                extra={"query": query[:100], "error": str(e)},
                exc_info=True,
            )
            return []
