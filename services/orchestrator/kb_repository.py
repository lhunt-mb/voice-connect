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

    content: str  # Retrieved or synthesized content
    sources: list[str]  # Source citations
    score: float = 0.0  # Relevance score


class KnowledgeBaseRepository:
    """Repository for Bedrock Knowledge Base semantic search operations.

    Supports two modes:
    1. Retrieve-only (fast, ~200-400ms): Returns raw document chunks
    2. RetrieveAndGenerate (slower, ~1-2s): Synthesizes results using an LLM

    Use retrieve-only for lower latency when the voice model can synthesize.
    """

    def __init__(self, settings: Settings):
        """Initialize the KB repository.

        Args:
            settings: Application settings with KB configuration
        """
        self.settings = settings
        self.bedrock_agent = create_bedrock_agent_runtime_client(settings)
        # Use retrieve-only mode for faster responses (configurable via settings)
        self.use_retrieve_only = getattr(settings, "kb_retrieve_only", True)

        if not settings.kb_knowledge_base_id:
            logger.warning("Knowledge Base ID not configured - KB queries will fail")

    async def search(
        self,
        query: str,
        max_results: int = 3,
        max_tokens: int = 512,
    ) -> list[KnowledgeBaseResult]:
        """Search Knowledge Base.

        Uses either Retrieve-only (fast) or RetrieveAndGenerate (slower) based on config.

        Args:
            query: Search query (with optional context prefix)
            max_results: Maximum number of document chunks to retrieve (default: 3)
            max_tokens: Maximum tokens in generated response (default: 512, only for RetrieveAndGenerate)

        Returns:
            List of KnowledgeBaseResult objects

        Note:
            Errors are handled gracefully - returns empty list if KB unavailable.
            This prevents voice call drops due to KB issues.
        """
        if not self.settings.kb_knowledge_base_id:
            logger.error("KB not configured", extra={"query": query})
            return []

        if self.use_retrieve_only:
            return await self._retrieve_only(query, max_results)
        else:
            return await self._retrieve_and_generate(query, max_results, max_tokens)

    async def _retrieve_only(
        self,
        query: str,
        max_results: int = 3,
    ) -> list[KnowledgeBaseResult]:
        """Fast retrieve-only search (~200-400ms).

        Returns raw document chunks without LLM synthesis.
        The voice model (OpenAI/Nova) will synthesize the response.
        """
        try:
            logger.info(
                "Querying Knowledge Base (retrieve-only)",
                extra={
                    "query": query[:100],
                    "kb_id": self.settings.kb_knowledge_base_id,
                    "max_results": max_results,
                },
            )

            response = await asyncio.to_thread(
                self.bedrock_agent.retrieve,
                knowledgeBaseId=self.settings.kb_knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": max_results,
                    }
                },
            )

            results = response.get("retrievalResults", [])

            if not results:
                logger.warning("No results from KB retrieve", extra={"query": query[:100]})
                return []

            # Combine top chunks into a single result
            chunks = []
            sources = []
            for result in results:
                content = result.get("content", {}).get("text", "")
                if content:
                    chunks.append(content)

                # Extract source
                location = result.get("location", {})
                s3_location = location.get("s3Location", {})
                uri = s3_location.get("uri", "")
                if uri:
                    sources.append(uri)

            # Remove duplicate sources
            sources = list(dict.fromkeys(sources))

            # Join chunks with separator
            combined_content = "\n\n---\n\n".join(chunks)

            logger.info(
                "KB retrieve successful",
                extra={
                    "query": query[:100],
                    "num_chunks": len(chunks),
                    "total_length": len(combined_content),
                    "num_sources": len(sources),
                },
            )

            return [
                KnowledgeBaseResult(
                    content=combined_content,
                    sources=sources,
                    score=results[0].get("score", 0.0) if results else 0.0,
                )
            ]

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            logger.error(
                "Bedrock KB retrieve failed",
                extra={
                    "query": query[:100],
                    "error_code": error_code,
                    "error_message": error_message,
                },
                exc_info=True,
            )
            return []

        except Exception as e:
            logger.error(
                "Unexpected error in KB retrieve",
                extra={"query": query[:100], "error": str(e)},
                exc_info=True,
            )
            return []

    async def _retrieve_and_generate(
        self,
        query: str,
        max_results: int = 3,
        max_tokens: int = 512,
    ) -> list[KnowledgeBaseResult]:
        """Slower RetrieveAndGenerate search (~1-2s).

        Returns LLM-synthesized response from retrieved documents.
        """
        try:
            logger.info(
                "Querying Knowledge Base (retrieve-and-generate)",
                extra={
                    "query": query[:100],
                    "kb_id": self.settings.kb_knowledge_base_id,
                    "max_results": max_results,
                },
            )

            response = await asyncio.to_thread(
                self.bedrock_agent.retrieve_and_generate,
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": self.settings.kb_knowledge_base_id,
                        "modelArn": f"arn:aws:bedrock:{self.settings.kb_region}::foundation-model/amazon.nova-micro-v1:0",
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": max_results,
                            }
                        },
                        "generationConfiguration": {
                            "inferenceConfig": {
                                "textInferenceConfig": {
                                    "maxTokens": max_tokens,
                                    "temperature": 0.0,
                                }
                            }
                        },
                    },
                },
            )

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

            sources = list(dict.fromkeys(sources))

            logger.info(
                "KB retrieve-and-generate successful",
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
                    score=1.0,
                )
            ]

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            logger.error(
                "Bedrock KB retrieve-and-generate failed",
                extra={
                    "query": query[:100],
                    "error_code": error_code,
                    "error_message": error_message,
                },
                exc_info=True,
            )
            return []

        except Exception as e:
            logger.error(
                "Unexpected error in KB retrieve-and-generate",
                extra={"query": query[:100], "error": str(e)},
                exc_info=True,
            )
            return []
