"""Strands Agent Runtime.

Configures the conversational agent with Bedrock Claude Sonnet model and
MCP client connections to Financial Research and Knowledge Base servers.
Provides async message processing with 30-second timeout handling.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from functools import partial

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient
from strands.types.agent import Limits

from agent.observability import (
    TraceCollector,
    collect_trace_from_agent_response,
    extract_token_counts,
)
from backend.constants import FINANCIAL_MCP_URL, KNOWLEDGE_BASE_MCP_URL
from backend.models.conversation import TraceData

logger = logging.getLogger(__name__)

# Agent configuration
MODEL_ID = "anthropic.claude-sonnet-4-20250514"
AWS_REGION = "us-east-1"
MAX_TOOL_CALLS = 10
REQUEST_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = (
    "You are a helpful AI assistant for an AWS class titled "
    "'Building Agentic AI with Amazon Bedrock AgentCore,' "
    "taught to employees of Ameriprise Financial. "
    "You have access to two sets of tools:\n\n"
    "1. **Financial Research tools** — retrieve stock quotes, company profiles, "
    "and market summaries for financial analysis relevant to Ameriprise Financial.\n"
    "2. **Knowledge Base tools** — query AWS Bedrock AgentCore documentation and "
    "course materials for retrieval-augmented generation.\n\n"
    "Use these tools to answer questions accurately. When you use a tool, explain "
    "what you found. If a tool returns an error, inform the user clearly and suggest "
    "they rephrase their question or try again later."
)


@dataclass
class ToolInvocationDetail:
    """Details of a single tool invocation during message processing."""

    mcp_server: str
    tool_name: str
    status: str  # "succeeded" or "failed"
    duration_ms: float


@dataclass
class AgentResponse:
    """Response from agent message processing."""

    text: str
    tool_invocations: list[ToolInvocationDetail] = field(default_factory=list)
    trace: TraceData | None = None
    timed_out: bool = False


def _create_financial_mcp_client() -> MCPClient:
    """Create MCP client for the Financial Research server."""
    return MCPClient(
        partial(streamablehttp_client, url=FINANCIAL_MCP_URL),
        prefix="financial_research",
    )


def _create_knowledge_base_mcp_client() -> MCPClient:
    """Create MCP client for the Knowledge Base server."""
    return MCPClient(
        partial(streamablehttp_client, url=KNOWLEDGE_BASE_MCP_URL),
        prefix="knowledge_base",
    )


def _create_model() -> BedrockModel:
    """Create the Bedrock model instance."""
    return BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
    )


def create_agent(
    model: BedrockModel | None = None,
    financial_mcp: MCPClient | None = None,
    knowledge_mcp: MCPClient | None = None,
) -> Agent:
    """Create and configure the Strands Agent with MCP tool connections.

    Args:
        model: Optional BedrockModel override (for testing).
        financial_mcp: Optional MCPClient override for Financial Research (for testing).
        knowledge_mcp: Optional MCPClient override for Knowledge Base (for testing).

    Returns:
        Configured Agent instance.
    """
    if model is None:
        model = _create_model()
    if financial_mcp is None:
        financial_mcp = _create_financial_mcp_client()
    if knowledge_mcp is None:
        knowledge_mcp = _create_knowledge_base_mcp_client()

    agent = Agent(
        model=model,
        tools=[financial_mcp, knowledge_mcp],
        system_prompt=SYSTEM_PROMPT,
    )
    return agent


async def process_message(agent: Agent, message: str) -> AgentResponse:
    """Process a user message through the agent with timeout handling.

    Invokes the agent with the given message, enforcing a maximum of 10
    tool invocations and a 30-second timeout. Returns the agent's response
    text along with tool invocation details and trace data.

    Automatically collects trace spans for:
    - User message receipt
    - Each tool invocation (MCP server name, tool name, duration, status)
    - LLM inference calls
    - Per-request metrics (latency, tool count, token counts)

    Args:
        agent: The configured Strands Agent instance.
        message: The user's message text.

    Returns:
        AgentResponse containing the response text, tool invocation details,
        trace data, and timeout status.
    """
    collector = TraceCollector()
    collector.start_request()

    # Record user message span
    collector.record_user_message()

    start_time = time.monotonic()

    try:
        result = await asyncio.wait_for(
            agent.invoke_async(
                message,
                limits=Limits(turns=MAX_TOOL_CALLS),
            ),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Agent request timed out after %d seconds", REQUEST_TIMEOUT_SECONDS)
        collector.end_request()
        trace_data = collector.build_trace_data()
        collector.emit(trace_data)
        return AgentResponse(
            text="Request timed out. The agent could not complete processing within 30 seconds. Please try a simpler question or try again later.",
            tool_invocations=[],
            trace=trace_data,
            timed_out=True,
        )
    except Exception as e:
        logger.error("Agent processing error: %s", str(e))
        collector.end_request()
        trace_data = collector.build_trace_data()
        collector.emit(trace_data)
        return AgentResponse(
            text=f"An error occurred while processing your request: {str(e)}",
            tool_invocations=[],
            trace=trace_data,
            timed_out=False,
        )

    # Collect trace spans from agent result
    collect_trace_from_agent_response(collector, result, start_time)

    # Extract token counts
    prompt_tokens, completion_tokens = extract_token_counts(result)

    # End the request timing
    collector.end_request()

    # Build trace data
    trace_data = collector.build_trace_data(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    # Emit trace data (falls back to file if AgentCore unavailable)
    collector.emit(trace_data)

    # Extract response text from result message
    response_text = _extract_response_text(result)

    # Extract tool invocation details from metrics/messages
    tool_invocations = _extract_tool_invocations(result, start_time)

    return AgentResponse(
        text=response_text,
        tool_invocations=tool_invocations,
        trace=trace_data,
        timed_out=False,
    )


def _extract_response_text(result) -> str:
    """Extract the text content from the agent result message."""
    if result.message and result.message.get("content"):
        text_parts = []
        for block in result.message["content"]:
            if isinstance(block, dict) and block.get("text"):
                text_parts.append(block["text"])
        if text_parts:
            return "\n".join(text_parts)
    return ""


def _extract_tool_invocations(result, start_time: float) -> list[ToolInvocationDetail]:
    """Extract tool invocation details from the agent result.

    Parses the agent's message history to find tool use blocks and their
    corresponding results to build invocation details.
    """
    invocations = []

    if not result.message or not result.message.get("content"):
        return invocations

    # Look through all messages in the agent's history for tool calls
    # The metrics contain cycle information we can use
    try:
        metrics = result.metrics
        if metrics and hasattr(metrics, "latest_agent_invocation"):
            latest = metrics.latest_agent_invocation
            if latest and hasattr(latest, "cycles"):
                for cycle in latest.cycles:
                    if hasattr(cycle, "tool_results"):
                        for tool_result in cycle.tool_results:
                            tool_name = getattr(tool_result, "name", "unknown")
                            status = "succeeded" if getattr(tool_result, "status", "") == "success" else "failed"
                            duration = getattr(tool_result, "duration_ms", 0.0)

                            # Determine MCP server from tool name prefix
                            mcp_server = _resolve_mcp_server(tool_name)

                            invocations.append(
                                ToolInvocationDetail(
                                    mcp_server=mcp_server,
                                    tool_name=_strip_prefix(tool_name),
                                    status=status,
                                    duration_ms=duration,
                                )
                            )
    except (AttributeError, TypeError):
        # If metrics structure doesn't match expectations, return empty list
        logger.debug("Could not extract tool invocations from agent metrics")

    return invocations


def _resolve_mcp_server(tool_name: str) -> str:
    """Resolve the MCP server name from the tool name prefix.

    Tools from MCP clients are prefixed with the client prefix (e.g.,
    'financial_research__get_stock_quote' or 'knowledge_base__query_knowledge_base').
    """
    if tool_name.startswith("financial_research"):
        return "financial-research"
    elif tool_name.startswith("knowledge_base"):
        return "knowledge-base"
    return "unknown"


def _strip_prefix(tool_name: str) -> str:
    """Strip the MCP client prefix from a tool name."""
    if "__" in tool_name:
        return tool_name.split("__", 1)[1]
    return tool_name
