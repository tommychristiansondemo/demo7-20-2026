"""Unit tests for the Knowledge Base MCP server."""

import json
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from mcp_servers.knowledge_base.server import (
    query_knowledge_base,
    _extract_source_title,
    _extract_section_id,
    _register_with_agentcore,
    health_check,
    mcp,
    RELEVANCE_THRESHOLD,
    MAX_QUERY_LENGTH,
)


class TestQueryValidation:
    """Tests for query input validation."""

    def test_empty_query_returns_invalid_query_error(self):
        result = query_knowledge_base("")
        parsed = json.loads(result)
        assert parsed["error_type"] == "INVALID_QUERY"
        assert "empty" in parsed["message"].lower()

    def test_whitespace_only_query_returns_invalid_query_error(self):
        result = query_knowledge_base("   ")
        parsed = json.loads(result)
        assert parsed["error_type"] == "INVALID_QUERY"
        assert "empty" in parsed["message"].lower()

    def test_query_exceeding_max_length_returns_invalid_query_error(self):
        long_query = "a" * (MAX_QUERY_LENGTH + 1)
        result = query_knowledge_base(long_query)
        parsed = json.loads(result)
        assert parsed["error_type"] == "INVALID_QUERY"
        assert "1000" in parsed["message"]

    def test_query_at_max_length_does_not_return_error(self):
        """A query of exactly 1000 characters should be accepted (not return INVALID_QUERY)."""
        valid_query = "a" * MAX_QUERY_LENGTH
        with patch(
            "mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client"
        ) as mock_client:
            mock_retrieve = MagicMock(return_value={"retrievalResults": []})
            mock_client.return_value.retrieve = mock_retrieve
            result = query_knowledge_base(valid_query)
            parsed = json.loads(result)
            # Should not be an error — should be a valid response
            assert "error_type" not in parsed
            assert "passages" in parsed

    def test_single_char_query_is_valid(self):
        """A single character query should be accepted."""
        with patch(
            "mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client"
        ) as mock_client:
            mock_retrieve = MagicMock(return_value={"retrievalResults": []})
            mock_client.return_value.retrieve = mock_retrieve
            result = query_knowledge_base("a")
            parsed = json.loads(result)
            assert "error_type" not in parsed
            assert "passages" in parsed


class TestRelevanceFiltering:
    """Tests for relevance score filtering."""

    def _mock_retrieve_response(self, results):
        """Helper to create a mocked retrieve response."""
        return {"retrievalResults": results}

    def _make_result(self, text, score, source_uri="s3://bucket/doc.pdf"):
        """Helper to create a single retrieval result."""
        return {
            "content": {"text": text},
            "score": score,
            "location": {
                "type": "S3",
                "s3Location": {"uri": source_uri},
            },
            "metadata": {},
        }

    @patch("mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client")
    def test_filters_passages_below_threshold(self, mock_client):
        results = [
            self._make_result("High relevance", 0.8),
            self._make_result("Low relevance", 0.1),
            self._make_result("At threshold", 0.3),
        ]
        mock_client.return_value.retrieve = MagicMock(
            return_value=self._mock_retrieve_response(results)
        )

        result = query_knowledge_base("test query")
        parsed = json.loads(result)

        assert len(parsed["passages"]) == 2
        scores = [p["relevance_score"] for p in parsed["passages"]]
        assert all(s >= RELEVANCE_THRESHOLD for s in scores)

    @patch("mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client")
    def test_returns_empty_list_with_message_when_no_passages_meet_threshold(self, mock_client):
        results = [
            self._make_result("Low 1", 0.1),
            self._make_result("Low 2", 0.2),
        ]
        mock_client.return_value.retrieve = MagicMock(
            return_value=self._mock_retrieve_response(results)
        )

        result = query_knowledge_base("test query")
        parsed = json.loads(result)

        assert parsed["passages"] == []
        assert parsed["message"] is not None
        assert "relevance" in parsed["message"].lower() or "threshold" in parsed["message"].lower()

    @patch("mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client")
    def test_returns_max_5_passages(self, mock_client):
        results = [self._make_result(f"Passage {i}", 0.9 - i * 0.05) for i in range(8)]
        mock_client.return_value.retrieve = MagicMock(
            return_value=self._mock_retrieve_response(results)
        )

        result = query_knowledge_base("test query")
        parsed = json.loads(result)

        assert len(parsed["passages"]) <= 5

    @patch("mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client")
    def test_passages_contain_required_fields(self, mock_client):
        results = [
            {
                "content": {"text": "Some relevant text about Bedrock."},
                "score": 0.85,
                "location": {
                    "type": "S3",
                    "s3Location": {"uri": "s3://my-bucket/docs/bedrock-guide.pdf"},
                },
                "metadata": {"section_id": "sec-001"},
            }
        ]
        mock_client.return_value.retrieve = MagicMock(
            return_value=self._mock_retrieve_response(results)
        )

        result = query_knowledge_base("What is Bedrock?")
        parsed = json.loads(result)

        assert len(parsed["passages"]) == 1
        passage = parsed["passages"][0]
        assert "text" in passage
        assert "source_title" in passage
        assert "section_id" in passage
        assert "relevance_score" in passage
        assert passage["text"] == "Some relevant text about Bedrock."
        assert passage["relevance_score"] == 0.85
        assert passage["section_id"] == "sec-001"

    @patch("mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client")
    def test_no_message_when_passages_found(self, mock_client):
        results = [self._make_result("Relevant content", 0.7)]
        mock_client.return_value.retrieve = MagicMock(
            return_value=self._mock_retrieve_response(results)
        )

        result = query_knowledge_base("test query")
        parsed = json.loads(result)

        assert parsed["message"] is None
        assert len(parsed["passages"]) == 1


class TestDataSourceError:
    """Tests for handling data source errors."""

    @patch("mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client")
    def test_returns_data_source_unavailable_on_exception(self, mock_client):
        mock_client.return_value.retrieve = MagicMock(
            side_effect=Exception("Connection timeout")
        )

        result = query_knowledge_base("test query")
        parsed = json.loads(result)

        assert parsed["error_type"] == "DATA_SOURCE_UNAVAILABLE"
        assert "Connection timeout" in parsed["message"]


class TestSourceTitleExtraction:
    """Tests for _extract_source_title helper."""

    def test_extracts_from_metadata_source_title(self):
        result = {"metadata": {"source_title": "AWS Bedrock Guide"}}
        assert _extract_source_title("", result) == "AWS Bedrock Guide"

    def test_extracts_from_metadata_title(self):
        result = {"metadata": {"title": "Course Materials"}}
        assert _extract_source_title("", result) == "Course Materials"

    def test_extracts_from_s3_uri(self):
        result = {"metadata": {}}
        assert _extract_source_title("s3://bucket/docs/bedrock-guide.pdf", result) == "bedrock guide"

    def test_returns_unknown_when_no_info(self):
        result = {"metadata": {}}
        assert _extract_source_title("", result) == "Unknown Source"


class TestSectionIdExtraction:
    """Tests for _extract_section_id helper."""

    def test_extracts_from_metadata_section_id(self):
        result = {"metadata": {"section_id": "sec-123"}, "location": {}}
        assert _extract_section_id(result) == "sec-123"

    def test_extracts_from_chunk_id(self):
        result = {"metadata": {"x-amz-bedrock-kb-chunk-id": "chunk-456"}, "location": {}}
        assert _extract_section_id(result) == "chunk-456"

    def test_extracts_from_s3_location(self):
        result = {
            "metadata": {},
            "location": {
                "type": "S3",
                "s3Location": {"uri": "s3://bucket/docs/chapter1.pdf"},
            },
        }
        assert _extract_section_id(result) == "s3:chapter1.pdf"

    def test_returns_unknown_when_no_info(self):
        result = {"metadata": {}, "location": {"type": "WEB"}}
        assert _extract_section_id(result) == "unknown"


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client for the MCP server's Starlette app."""
        from starlette.testclient import TestClient

        app = mcp.streamable_http_app()
        return TestClient(app)

    def test_health_endpoint_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_endpoint_returns_correct_body(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "knowledge-base-mcp"


class TestAgentCoreRegistration:
    """Tests for AgentCore registration logic."""

    @patch("mcp_servers.knowledge_base.server.AGENTCORE_ENABLED", False)
    def test_registration_skipped_when_disabled(self):
        """Registration should be skipped when AGENTCORE_ENABLED is false."""
        with patch("mcp_servers.knowledge_base.server.boto3") as mock_boto3:
            _register_with_agentcore()
            mock_boto3.client.assert_not_called()

    @patch("mcp_servers.knowledge_base.server.AGENTCORE_ENABLED", True)
    @patch("mcp_servers.knowledge_base.server.boto3")
    def test_registration_calls_agentcore_when_enabled(self, mock_boto3):
        """Registration should call AgentCore API when enabled."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        _register_with_agentcore()

        mock_boto3.client.assert_called_once_with("bedrock-agentcore", region_name="us-east-1")
        mock_client.register_mcp_server.assert_called_once()
        call_kwargs = mock_client.register_mcp_server.call_args[1]
        assert call_kwargs["name"] == "knowledge-base-mcp"
        assert "query_knowledge_base" in call_kwargs["tools"]

    @patch("mcp_servers.knowledge_base.server.AGENTCORE_ENABLED", True)
    @patch("mcp_servers.knowledge_base.server.boto3")
    def test_registration_failure_does_not_raise(self, mock_boto3):
        """Registration failure should not crash the server."""
        mock_client = MagicMock()
        mock_client.register_mcp_server.side_effect = Exception("Service unavailable")
        mock_boto3.client.return_value = mock_client

        # Should not raise
        _register_with_agentcore()
