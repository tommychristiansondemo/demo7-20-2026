"""Agent observability and trace span emission.

Provides a TraceCollector class for collecting trace spans during agent
processing, emitting them via AgentCore observability, and falling back
to file logging when emission fails.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.models.conversation import SpanStatus, TraceData, TraceSpan

logger = logging.getLogger(__name__)

# Fallback log file path for when trace emission fails
FALLBACK_LOG_PATH = Path("/var/log/agentcore-demo/observability-fallback.log")


@dataclass
class SpanRecord:
    """Internal record of a trace span collected during processing."""

    name: str
    mcp_server: str | None = None
    tool_name: str | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    status: SpanStatus = SpanStatus.SUCCESS

    @property
    def duration_ms(self) -> float:
        """Calculate duration in milliseconds."""
        return max(0.0, (self.end_time - self.start_time) * 1000)


class TraceCollector:
    """Collects trace spans during agent processing and emits them via AgentCore.

    Usage:
        collector = TraceCollector()
        collector.start_request()

        # Record spans during processing
        with collector.span("user_message"):
            ...
        with collector.tool_span("financial-research", "get_stock_quote"):
            ...
        with collector.span("llm_inference"):
            ...

        # Generate trace data
        trace_data = collector.build_trace_data(prompt_tokens=100, completion_tokens=50)

        # Emit to AgentCore (with fallback)
        collector.emit(trace_data)
    """

    def __init__(self) -> None:
        self._spans: list[SpanRecord] = []
        self._request_start: float = 0.0
        self._request_end: float = 0.0
        self._tool_call_count: int = 0

    def start_request(self) -> None:
        """Mark the start of a new agent request. Resets all collected spans."""
        self._spans = []
        self._request_start = time.monotonic()
        self._request_end = 0.0
        self._tool_call_count = 0

    def end_request(self) -> None:
        """Mark the end of the current agent request."""
        self._request_end = time.monotonic()

    @property
    def total_latency_ms(self) -> float:
        """Total latency from request start to end in milliseconds."""
        end = self._request_end if self._request_end > 0 else time.monotonic()
        return max(0.0, (end - self._request_start) * 1000)

    @property
    def tool_call_count(self) -> int:
        """Number of tool invocations recorded."""
        return self._tool_call_count

    def record_span(
        self,
        name: str,
        duration_ms: float,
        status: SpanStatus = SpanStatus.SUCCESS,
        mcp_server: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Record a completed span directly with known duration.

        Args:
            name: Name of the span (e.g., "user_message", "llm_inference", "tool_call").
            duration_ms: Duration in milliseconds.
            status: Whether the span succeeded or failed.
            mcp_server: MCP server name if this is a tool call span.
            tool_name: Tool name if this is a tool call span.
        """
        now = time.monotonic()
        span = SpanRecord(
            name=name,
            mcp_server=mcp_server,
            tool_name=tool_name,
            start_time=now - (duration_ms / 1000),
            end_time=now,
            status=status,
        )
        self._spans.append(span)
        if mcp_server is not None or tool_name is not None:
            self._tool_call_count += 1

    def record_tool_span(
        self,
        mcp_server: str,
        tool_name: str,
        duration_ms: float,
        status: SpanStatus = SpanStatus.SUCCESS,
    ) -> None:
        """Record a tool invocation span.

        Args:
            mcp_server: Name of the MCP server invoked.
            tool_name: Name of the tool called.
            duration_ms: Duration in milliseconds.
            status: Whether the tool call succeeded or failed.
        """
        self.record_span(
            name=f"tool_call:{mcp_server}/{tool_name}",
            duration_ms=duration_ms,
            status=status,
            mcp_server=mcp_server,
            tool_name=tool_name,
        )

    def record_user_message(self) -> None:
        """Record that a user message was received."""
        self.record_span(name="user_message", duration_ms=0.0, status=SpanStatus.SUCCESS)
        logger.info("Observability: user message received")

    def record_llm_inference(
        self,
        duration_ms: float,
        status: SpanStatus = SpanStatus.SUCCESS,
    ) -> None:
        """Record an LLM inference call.

        Args:
            duration_ms: Duration of the inference call in milliseconds.
            status: Whether the inference succeeded or failed.
        """
        self.record_span(name="llm_inference", duration_ms=duration_ms, status=status)
        logger.info("Observability: LLM inference completed in %.1fms", duration_ms)

    def build_trace_data(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> TraceData:
        """Build a TraceData object from all collected spans.

        Args:
            prompt_tokens: Number of prompt tokens used in this request.
            completion_tokens: Number of completion tokens generated.

        Returns:
            TraceData instance matching the Pydantic model in backend/models/conversation.py.
        """
        spans = [
            TraceSpan(
                name=record.name,
                mcp_server=record.mcp_server,
                tool_name=record.tool_name,
                duration_ms=record.duration_ms,
                status=record.status,
            )
            for record in self._spans
        ]

        return TraceData(
            total_latency_ms=self.total_latency_ms,
            tool_call_count=self._tool_call_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            spans=spans,
        )

    def emit(self, trace_data: TraceData) -> bool:
        """Emit trace data via AgentCore observability.

        Attempts to send trace data to AgentCore. If emission fails,
        falls back to writing to a local log file. Processing continues
        regardless of emission success.

        Args:
            trace_data: The complete trace data to emit.

        Returns:
            True if emission succeeded via AgentCore, False if fallback was used.
        """
        try:
            _emit_to_agentcore(trace_data)
            logger.info(
                "Trace emitted: latency=%.1fms, tools=%d, prompt_tokens=%d, completion_tokens=%d",
                trace_data.total_latency_ms,
                trace_data.tool_call_count,
                trace_data.prompt_tokens,
                trace_data.completion_tokens,
            )
            return True
        except Exception as e:
            logger.warning("Failed to emit trace to AgentCore: %s. Using fallback.", str(e))
            _write_fallback_log(trace_data, error=str(e))
            return False


def _emit_to_agentcore(trace_data: TraceData) -> None:
    """Emit trace data to Bedrock AgentCore observability service.

    This function sends the trace data to AgentCore's tracing API.
    In the demo environment, this integrates with the AgentCore
    observability endpoint. If AgentCore is unavailable, an exception
    is raised to trigger fallback logging.

    Args:
        trace_data: The trace data to emit.

    Raises:
        Exception: If the emission fails for any reason.
    """
    # AgentCore observability integration point.
    # In production, this would call the AgentCore tracing API via boto3:
    #   client = boto3.client('bedrock-agentcore')
    #   client.put_trace(...)
    # For the demo, we log structured trace data which AgentCore can ingest.
    logger.info(
        "AgentCore trace: %s",
        json.dumps(trace_data.model_dump(), default=str),
    )


def _write_fallback_log(trace_data: TraceData, error: str) -> None:
    """Write trace data to fallback log file when AgentCore emission fails.

    Ensures the agent continues processing even when observability
    infrastructure is unavailable. The fallback log can be collected
    and replayed to AgentCore once the service recovers.

    Args:
        trace_data: The trace data that failed to emit.
        error: The error message from the failed emission attempt.
    """
    fallback_entry = {
        "error": error,
        "trace_data": trace_data.model_dump(),
        "timestamp": time.time(),
    }

    try:
        # Ensure the directory exists
        FALLBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FALLBACK_LOG_PATH, "a") as f:
            f.write(json.dumps(fallback_entry, default=str) + "\n")
        logger.info("Trace data written to fallback log: %s", FALLBACK_LOG_PATH)
    except OSError as file_error:
        # If even fallback logging fails, log to stderr and continue
        logger.error(
            "Failed to write to fallback log (%s): %s. Trace data: %s",
            FALLBACK_LOG_PATH,
            str(file_error),
            json.dumps(fallback_entry, default=str),
        )


def collect_trace_from_agent_response(
    collector: TraceCollector,
    result,
    start_time: float,
) -> None:
    """Extract trace information from an agent result and record spans.

    Parses the agent's metrics to extract tool invocation details and
    LLM inference information, recording them as spans in the collector.

    Args:
        collector: The TraceCollector accumulating spans for this request.
        result: The agent result object from strands Agent.invoke_async().
        start_time: The monotonic time when the request started.
    """
    if result is None:
        return

    # Extract tool invocation spans from agent metrics
    try:
        metrics = result.metrics
        if metrics and hasattr(metrics, "latest_agent_invocation"):
            latest = metrics.latest_agent_invocation
            if latest and hasattr(latest, "cycles"):
                for cycle in latest.cycles:
                    if hasattr(cycle, "tool_results"):
                        for tool_result in cycle.tool_results:
                            tool_name_raw = getattr(tool_result, "name", "unknown")
                            status_str = getattr(tool_result, "status", "")
                            duration = getattr(tool_result, "duration_ms", 0.0)

                            # Determine MCP server from tool name prefix
                            mcp_server = _resolve_mcp_server(tool_name_raw)
                            tool_name = _strip_prefix(tool_name_raw)
                            span_status = (
                                SpanStatus.SUCCESS if status_str == "success" else SpanStatus.FAILURE
                            )

                            collector.record_tool_span(
                                mcp_server=mcp_server,
                                tool_name=tool_name,
                                duration_ms=duration,
                                status=span_status,
                            )

                            logger.info(
                                "Observability: tool invocation %s/%s duration=%.1fms status=%s",
                                mcp_server,
                                tool_name,
                                duration,
                                span_status.value,
                            )
    except (AttributeError, TypeError):
        logger.debug("Could not extract tool invocation spans from agent metrics")

    # Record LLM inference span (total time minus tool calls is approximate LLM time)
    total_elapsed_ms = (time.monotonic() - start_time) * 1000
    tool_time_ms = sum(
        span.duration_ms for span in collector._spans if span.mcp_server is not None
    )
    llm_duration_ms = max(0.0, total_elapsed_ms - tool_time_ms)
    collector.record_llm_inference(duration_ms=llm_duration_ms)


def extract_token_counts(result) -> tuple[int, int]:
    """Extract prompt and completion token counts from agent result.

    Args:
        result: The agent result object from strands Agent.invoke_async().

    Returns:
        Tuple of (prompt_tokens, completion_tokens).
    """
    prompt_tokens = 0
    completion_tokens = 0

    try:
        metrics = result.metrics
        if metrics and hasattr(metrics, "latest_agent_invocation"):
            latest = metrics.latest_agent_invocation
            if latest and hasattr(latest, "usage"):
                usage = latest.usage
                prompt_tokens = getattr(usage, "inputTokens", 0) or 0
                completion_tokens = getattr(usage, "outputTokens", 0) or 0
            elif latest and hasattr(latest, "cycles"):
                # Sum tokens across all cycles
                for cycle in latest.cycles:
                    if hasattr(cycle, "usage"):
                        cycle_usage = cycle.usage
                        prompt_tokens += getattr(cycle_usage, "inputTokens", 0) or 0
                        completion_tokens += getattr(cycle_usage, "outputTokens", 0) or 0
    except (AttributeError, TypeError):
        logger.debug("Could not extract token counts from agent metrics")

    return prompt_tokens, completion_tokens


def _resolve_mcp_server(tool_name: str) -> str:
    """Resolve the MCP server name from the tool name prefix."""
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
