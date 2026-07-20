"""Unit tests for agent observability and trace span emission."""

import time
from unittest.mock import MagicMock, patch

import pytest

from agent.observability import (
    FALLBACK_LOG_PATH,
    TraceCollector,
    _emit_to_agentcore,
    _write_fallback_log,
    collect_trace_from_agent_response,
    extract_token_counts,
)
from backend.models.conversation import SpanStatus, TraceData, TraceSpan


class TestTraceCollector:
    """Tests for TraceCollector class."""

    def test_start_request_resets_state(self):
        collector = TraceCollector()
        collector.record_span("test", duration_ms=10.0)
        collector.start_request()
        trace = collector.build_trace_data()
        assert trace.spans == []
        assert trace.tool_call_count == 0

    def test_record_span_basic(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_span("user_message", duration_ms=0.0)
        trace = collector.build_trace_data()
        assert len(trace.spans) == 1
        assert trace.spans[0].name == "user_message"
        assert trace.spans[0].status == SpanStatus.SUCCESS

    def test_record_tool_span(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_tool_span(
            mcp_server="financial-research",
            tool_name="get_stock_quote",
            duration_ms=150.5,
            status=SpanStatus.SUCCESS,
        )
        trace = collector.build_trace_data()
        assert len(trace.spans) == 1
        assert trace.spans[0].mcp_server == "financial-research"
        assert trace.spans[0].tool_name == "get_stock_quote"
        assert trace.spans[0].duration_ms == pytest.approx(150.5, abs=1.0)
        assert trace.spans[0].status == SpanStatus.SUCCESS
        assert trace.tool_call_count == 1

    def test_record_tool_span_failure(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_tool_span(
            mcp_server="knowledge-base",
            tool_name="query_knowledge_base",
            duration_ms=200.0,
            status=SpanStatus.FAILURE,
        )
        trace = collector.build_trace_data()
        assert trace.spans[0].status == SpanStatus.FAILURE

    def test_tool_call_count_tracks_only_tool_spans(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_span("user_message", duration_ms=0.0)
        collector.record_span("llm_inference", duration_ms=500.0)
        collector.record_tool_span("financial-research", "get_stock_quote", 100.0)
        collector.record_tool_span("knowledge-base", "query_knowledge_base", 200.0)
        assert collector.tool_call_count == 2
        trace = collector.build_trace_data()
        assert trace.tool_call_count == 2

    def test_total_latency_ms(self):
        collector = TraceCollector()
        collector.start_request()
        time.sleep(0.01)  # 10ms
        collector.end_request()
        assert collector.total_latency_ms >= 10.0

    def test_record_user_message(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_user_message()
        trace = collector.build_trace_data()
        assert trace.spans[0].name == "user_message"

    def test_record_llm_inference(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_llm_inference(duration_ms=1234.5)
        trace = collector.build_trace_data()
        assert trace.spans[0].name == "llm_inference"
        assert trace.spans[0].duration_ms == pytest.approx(1234.5, abs=1.0)

    def test_build_trace_data_with_tokens(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_user_message()
        collector.record_tool_span("financial-research", "get_stock_quote", 100.0)
        collector.end_request()
        trace = collector.build_trace_data(prompt_tokens=500, completion_tokens=200)
        assert trace.prompt_tokens == 500
        assert trace.completion_tokens == 200
        assert trace.tool_call_count == 1
        assert trace.total_latency_ms >= 0.0
        assert len(trace.spans) == 2

    def test_build_trace_data_returns_pydantic_model(self):
        collector = TraceCollector()
        collector.start_request()
        collector.end_request()
        trace = collector.build_trace_data()
        assert isinstance(trace, TraceData)

    def test_multiple_tool_spans_ordered(self):
        collector = TraceCollector()
        collector.start_request()
        collector.record_tool_span("financial-research", "get_stock_quote", 100.0)
        collector.record_tool_span("financial-research", "get_company_profile", 150.0)
        collector.record_tool_span("knowledge-base", "query_knowledge_base", 200.0)
        trace = collector.build_trace_data()
        assert len(trace.spans) == 3
        assert trace.tool_call_count == 3
        assert trace.spans[0].tool_name == "get_stock_quote"
        assert trace.spans[1].tool_name == "get_company_profile"
        assert trace.spans[2].tool_name == "query_knowledge_base"


class TestEmitTrace:
    """Tests for trace emission and fallback logging."""

    def test_emit_success(self):
        collector = TraceCollector()
        collector.start_request()
        collector.end_request()
        trace = collector.build_trace_data()
        # Should not raise and return True
        result = collector.emit(trace)
        assert result is True

    @patch("agent.observability._emit_to_agentcore")
    def test_emit_fallback_on_failure(self, mock_emit):
        mock_emit.side_effect = Exception("AgentCore unavailable")
        collector = TraceCollector()
        collector.start_request()
        collector.end_request()
        trace = collector.build_trace_data()
        with patch("agent.observability._write_fallback_log") as mock_fallback:
            result = collector.emit(trace)
            assert result is False
            mock_fallback.assert_called_once()

    @patch("agent.observability._emit_to_agentcore")
    def test_emit_continues_processing_on_failure(self, mock_emit):
        """Verify that processing continues even when emission fails (Req 9.5)."""
        mock_emit.side_effect = RuntimeError("Connection refused")
        collector = TraceCollector()
        collector.start_request()
        collector.record_tool_span("financial-research", "get_stock_quote", 100.0)
        collector.end_request()
        trace = collector.build_trace_data()
        # Should not raise - continues processing
        with patch("agent.observability._write_fallback_log"):
            result = collector.emit(trace)
        assert result is False
        # Trace data is still valid
        assert trace.tool_call_count == 1


class TestCollectTraceFromAgentResponse:
    """Tests for extracting trace info from agent results."""

    def test_none_result(self):
        collector = TraceCollector()
        collector.start_request()
        collect_trace_from_agent_response(collector, None, time.monotonic())
        trace = collector.build_trace_data()
        # Should only have the llm_inference span from the end
        # Actually with None result, no spans are added for tools
        assert collector.tool_call_count == 0

    def test_result_with_tool_metrics(self):
        collector = TraceCollector()
        collector.start_request()

        # Create mock result with tool metrics
        mock_tool_result = MagicMock()
        mock_tool_result.name = "financial_research__get_stock_quote"
        mock_tool_result.status = "success"
        mock_tool_result.duration_ms = 150.0

        mock_cycle = MagicMock()
        mock_cycle.tool_results = [mock_tool_result]

        mock_latest = MagicMock()
        mock_latest.cycles = [mock_cycle]

        mock_metrics = MagicMock()
        mock_metrics.latest_agent_invocation = mock_latest

        mock_result = MagicMock()
        mock_result.metrics = mock_metrics

        start_time = time.monotonic()
        collect_trace_from_agent_response(collector, mock_result, start_time)

        trace = collector.build_trace_data()
        # Should have tool span + llm_inference span
        tool_spans = [s for s in trace.spans if s.tool_name is not None]
        assert len(tool_spans) == 1
        assert tool_spans[0].mcp_server == "financial-research"
        assert tool_spans[0].tool_name == "get_stock_quote"
        assert tool_spans[0].duration_ms == pytest.approx(150.0, abs=1.0)
        assert tool_spans[0].status == SpanStatus.SUCCESS

    def test_result_with_failed_tool(self):
        collector = TraceCollector()
        collector.start_request()

        mock_tool_result = MagicMock()
        mock_tool_result.name = "knowledge_base__query_knowledge_base"
        mock_tool_result.status = "error"
        mock_tool_result.duration_ms = 50.0

        mock_cycle = MagicMock()
        mock_cycle.tool_results = [mock_tool_result]

        mock_latest = MagicMock()
        mock_latest.cycles = [mock_cycle]

        mock_metrics = MagicMock()
        mock_metrics.latest_agent_invocation = mock_latest

        mock_result = MagicMock()
        mock_result.metrics = mock_metrics

        collect_trace_from_agent_response(collector, mock_result, time.monotonic())

        trace = collector.build_trace_data()
        tool_spans = [s for s in trace.spans if s.tool_name is not None]
        assert len(tool_spans) == 1
        assert tool_spans[0].status == SpanStatus.FAILURE


class TestExtractTokenCounts:
    """Tests for extracting token counts from agent results."""

    def test_none_result(self):
        prompt, completion = extract_token_counts(None)
        assert prompt == 0
        assert completion == 0

    def test_result_with_usage(self):
        mock_usage = MagicMock()
        mock_usage.inputTokens = 500
        mock_usage.outputTokens = 200

        mock_latest = MagicMock()
        mock_latest.usage = mock_usage

        mock_metrics = MagicMock()
        mock_metrics.latest_agent_invocation = mock_latest

        mock_result = MagicMock()
        mock_result.metrics = mock_metrics

        prompt, completion = extract_token_counts(mock_result)
        assert prompt == 500
        assert completion == 200

    def test_result_with_cycle_usage(self):
        mock_cycle_usage = MagicMock()
        mock_cycle_usage.inputTokens = 300
        mock_cycle_usage.outputTokens = 100

        mock_cycle = MagicMock()
        mock_cycle.usage = mock_cycle_usage

        mock_latest = MagicMock()
        mock_latest.usage = None
        mock_latest.cycles = [mock_cycle]
        # Ensure hasattr check works correctly
        del mock_latest.usage

        mock_metrics = MagicMock()
        mock_metrics.latest_agent_invocation = mock_latest

        mock_result = MagicMock()
        mock_result.metrics = mock_metrics

        prompt, completion = extract_token_counts(mock_result)
        assert prompt == 300
        assert completion == 100

    def test_result_with_missing_metrics(self):
        mock_result = MagicMock()
        mock_result.metrics = None
        prompt, completion = extract_token_counts(mock_result)
        assert prompt == 0
        assert completion == 0
