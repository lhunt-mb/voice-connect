"""Tool executor for handling Knowledge Base search tool calls from voice AI providers."""

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from services.orchestrator.kb_repository import KnowledgeBaseRepository
from shared.langfuse_tracing import ToolSpan

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result from executing a tool."""

    tool_name: str
    result: str
    success: bool
    error_message: str | None = None
    triggers_escalation: bool = False  # Signals that escalation should be triggered


class ToolExecutor:
    """Executes tool calls against backend services.

    Handles 5 tools:
    - search_products: Product eligibility and criteria
    - search_needs: Client needs to product mapping
    - search_service_providers: Lawyer profiles and matching
    - search_guardrails: Compliance rules and tone guidelines
    - escalate_to_human: Trigger handover to human agent

    Search tools query the Bedrock Knowledge Base with different
    context to focus retrieval on the relevant document types.
    """

    # Map tool names to search contexts
    # Context helps Bedrock KB focus on the right subset of documents
    TOOL_CONTEXTS = {
        "search_products": "legal service products, eligibility criteria, ineligibility criteria",
        "search_needs": "client needs, client situations, associated products",
        "search_service_providers": "lawyers, service providers, lawyer profiles, jurisdictions",
        "search_guardrails": "compliance rules, guardrails, tone guidelines, regulatory requirements",
    }

    # Maximum length for voice responses (avoid overwhelming callers)
    MAX_RESPONSE_LENGTH = 2048

    def __init__(
        self,
        kb_repository: KnowledgeBaseRepository,
        escalation_callback: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ):
        """Initialize the tool executor.

        Args:
            kb_repository: Repository for querying Bedrock Knowledge Base
            escalation_callback: Optional async callback to trigger escalation with reason
        """
        self.kb_repo = kb_repository
        self.escalation_callback = escalation_callback

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        conversation_id: str | None = None,
    ) -> ToolResult:
        """Execute a tool and return the result.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments (must contain "query" key for search tools, "reason" for escalation)
            conversation_id: Associated conversation ID for tracing

        Returns:
            ToolResult with success status and result/error message
        """
        # Wrap execution in Langfuse tracing span
        with ToolSpan(tool_name, arguments, conversation_id) as span:
            # Handle escalation tool specially
            if tool_name == "escalate_to_human":
                return await self._handle_escalation(arguments, conversation_id, span)

            # Validate tool name for search tools
            if tool_name not in self.TOOL_CONTEXTS:
                logger.error("Unknown tool", extra={"tool_name": tool_name})
                result = ToolResult(
                    tool_name=tool_name,
                    result="Unknown tool",
                    success=False,
                    error_message=f"Tool {tool_name} not found",
                )
                span.set_output(result.result, success=False)
                return result

            # Extract query from arguments
            query = arguments.get("query")
            if not query:
                logger.error("Missing query parameter", extra={"tool_name": tool_name, "arguments": arguments})
                result = ToolResult(
                    tool_name=tool_name,
                    result="No query provided",
                    success=False,
                    error_message="Query parameter is required",
                )
                span.set_output(result.result, success=False)
                return result

            # Add context to query for better retrieval
            # Example: "legal service products, eligibility criteria: 30-minute consultation"
            context = self.TOOL_CONTEXTS[tool_name]
            context_query = f"{context}: {query}"

            logger.info(
                "Executing tool",
                extra={
                    "tool_name": tool_name,
                    "query": query[:100],  # Log first 100 chars
                    "context": context,
                },
            )

            # Query Knowledge Base
            try:
                results = await self.kb_repo.search(context_query, max_results=5)

                if not results:
                    logger.warning(
                        "No results from KB",
                        extra={"tool_name": tool_name, "query": query[:100]},
                    )
                    result = ToolResult(
                        tool_name=tool_name,
                        result="I couldn't find information about that.",
                        success=False,
                    )
                    span.set_output(result.result, success=False)
                    return result

                # Get first result (highest relevance)
                content = results[0].content

                # Truncate for voice if too long, breaking at sentence boundaries
                # Voice callers can't process long responses
                if len(content) > self.MAX_RESPONSE_LENGTH:
                    content = self._truncate_at_sentence(content, self.MAX_RESPONSE_LENGTH)
                    logger.info(
                        "Truncated response for voice",
                        extra={
                            "tool_name": tool_name,
                            "original_length": len(results[0].content),
                            "truncated_length": len(content),
                        },
                    )

                logger.info(
                    "Tool execution successful",
                    extra={
                        "tool_name": tool_name,
                        "query": query[:100],
                        "response_length": len(content),
                        "num_sources": len(results[0].sources),
                    },
                )

                result = ToolResult(
                    tool_name=tool_name,
                    result=content,
                    success=True,
                )
                span.set_output(result.result, success=True)
                return result

            except Exception as e:
                logger.error(
                    "Tool execution failed",
                    extra={"tool_name": tool_name, "query": query[:100], "error": str(e)},
                    exc_info=True,
                )
                result = ToolResult(
                    tool_name=tool_name,
                    result="Sorry, I encountered an error searching for that information.",
                    success=False,
                    error_message=str(e),
                )
                span.set_output(result.result, success=False)
                return result

    def _truncate_at_sentence(self, text: str, max_length: int) -> str:
        """Truncate text at sentence boundary for better voice experience.

        Args:
            text: Text to truncate
            max_length: Maximum length

        Returns:
            Truncated text ending at a sentence boundary, or at word boundary if no good sentence break found
        """
        if len(text) <= max_length:
            return text

        # Truncate to max length
        truncated = text[:max_length]

        # Find last complete sentence within limit (look for . ! ?)
        last_period = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )

        # If we found a sentence break and it's at least 70% of the content, use it
        if last_period > max_length * 0.7:
            return truncated[: last_period + 1]

        # No good sentence break found, truncate at last word boundary
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:
            return truncated[:last_space] + "..."

        # Fallback to hard truncation (shouldn't happen often)
        return truncated + "..."

    async def _handle_escalation(
        self,
        arguments: dict[str, Any],
        conversation_id: str | None,
        span: ToolSpan,
    ) -> ToolResult:
        """Handle the escalate_to_human tool call.

        Args:
            arguments: Tool arguments containing "reason"
            conversation_id: Associated conversation ID for tracing
            span: Langfuse tracing span

        Returns:
            ToolResult signaling escalation should be triggered
        """
        reason = arguments.get("reason", "AI requested escalation")

        logger.info(
            "AI triggered escalation",
            extra={
                "conversation_id": conversation_id,
                "reason": reason,
            },
        )

        # Call the escalation callback if provided
        if self.escalation_callback:
            try:
                await self.escalation_callback(reason)
            except Exception as e:
                logger.error(
                    "Escalation callback failed",
                    extra={"conversation_id": conversation_id, "error": str(e)},
                    exc_info=True,
                )

        result = ToolResult(
            tool_name="escalate_to_human",
            result="Transferring you to a team member now. Please hold.",
            success=True,
            triggers_escalation=True,
        )
        span.set_output(result.result, success=True)
        return result
