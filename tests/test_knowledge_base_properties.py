"""Property-based tests for Knowledge Base MCP Server.

Feature: bedrock-agentcore-demo, Property 6: Knowledge base query response structure
Feature: bedrock-agentcore-demo, Property 7: Relevance score filtering
Feature: bedrock-agentcore-demo, Property 8: Knowledge base query validation

Validates: Requirements 4.3, 4.4, 4.5, 4.7
"""

import json
import random
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from mcp_servers.knowledge_base.server import (
    query_knowledge_base,
    MAX_QUERY_LENGTH,
    RELEVANCE_THRESHOLD,
    MAX_PASSAGES,
)


# Strategy: valid query strings (1-1000 characters, non-whitespace-only)
valid_query_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z"), exclude_characters="\x00"),
    min_size=1,
    max_size=MAX_QUERY_LENGTH,
).filter(lambda s: s.strip())


# Strategy: empty or whitespace-only queries
empty_query_strategy = st.one_of(
    st.just(""),
    st.text(alphabet=" \t\n\r", min_size=1, max_size=20),
)

# Strategy: queries exceeding max length
oversized_query_strategy = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=MAX_QUERY_LENGTH + 1,
    max_size=MAX_QUERY_LENGTH + 200,
)

# Strategy: relevance scores across the full range [0.0, 1.0]
relevance_score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy: number of mock results returned by bedrock (0 to 10)
num_results_strategy = st.integers(min_value=0, max_value=10)


def _make_mock_retrieval_result(text: str, score: float, source_uri: str = "s3://bucket/doc.pdf", section_id: str = "sec-001"):
    """Create a mock Bedrock KB retrieval result."""
    return {
        "content": {"text": text},
        "score": score,
        "location": {
            "type": "S3",
            "s3Location": {"uri": source_uri},
        },
        "metadata": {"section_id": section_id},
    }


def _make_mock_retrieve_response(num_results: int, scores: list[float]):
    """Create a complete mock retrieve response with given scores."""
    results = []
    for i, score in enumerate(scores[:num_results]):
        results.append(
            _make_mock_retrieval_result(
                text=f"Passage content {i} about AWS Bedrock AgentCore.",
                score=score,
                source_uri=f"s3://kb-bucket/docs/document-{i}.pdf",
                section_id=f"section-{i:03d}",
            )
        )
    return {"retrievalResults": results}


class TestKnowledgeBaseQueryResponseStructure:
    """Feature: bedrock-agentcore-demo, Property 6: Knowledge base query response structure"""

    @given(
        query=valid_query_strategy,
        num_results=num_results_strategy,
        scores=st.lists(
            st.floats(min_value=0.3, max_value=1.0, allow_nan=False),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_valid_query_returns_at_most_5_passages_with_required_fields(self, query, num_results, scores):
        """Feature: bedrock-agentcore-demo, Property 6: Knowledge base query response structure

        For any valid query string (1-1000 characters), the query_knowledge_base tool
        SHALL return at most 5 passages, each containing text, source_title, section_id,
        and relevance_score fields.

        Validates: Requirements 4.3
        """
        mock_response = _make_mock_retrieve_response(num_results, scores)

        with patch(
            "mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client"
        ) as mock_client:
            mock_client.return_value.retrieve = MagicMock(return_value=mock_response)

            result = query_knowledge_base(query)
            parsed = json.loads(result)

        # Must not be an error
        assert "error_type" not in parsed, (
            f"Expected valid response for query of length {len(query)}, "
            f"got error: {parsed}"
        )

        # Must contain passages field
        assert "passages" in parsed
        passages = parsed["passages"]

        # Must return at most 5 passages
        assert len(passages) <= MAX_PASSAGES, (
            f"Expected at most {MAX_PASSAGES} passages, got {len(passages)}"
        )

        # Each passage must have required fields
        for i, passage in enumerate(passages):
            assert "text" in passage, f"Passage {i} missing 'text'"
            assert isinstance(passage["text"], str), f"Passage {i} 'text' not a string"

            assert "source_title" in passage, f"Passage {i} missing 'source_title'"
            assert isinstance(passage["source_title"], str), f"Passage {i} 'source_title' not a string"

            assert "section_id" in passage, f"Passage {i} missing 'section_id'"
            assert isinstance(passage["section_id"], str), f"Passage {i} 'section_id' not a string"

            assert "relevance_score" in passage, f"Passage {i} missing 'relevance_score'"
            assert isinstance(passage["relevance_score"], (int, float)), (
                f"Passage {i} 'relevance_score' not a number"
            )


class TestRelevanceScoreFiltering:
    """Feature: bedrock-agentcore-demo, Property 7: Relevance score filtering"""

    @given(
        query=valid_query_strategy,
        scores=st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_all_returned_passages_meet_relevance_threshold(self, query, scores):
        """Feature: bedrock-agentcore-demo, Property 7: Relevance score filtering

        For any knowledge base query, all returned passages SHALL have a relevance_score
        at or above 0.3, and if no passages meet this threshold, the result SHALL be an
        empty passage list with an explanatory message.

        Validates: Requirements 4.4, 4.5
        """
        mock_response = _make_mock_retrieve_response(len(scores), scores)

        with patch(
            "mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client"
        ) as mock_client:
            mock_client.return_value.retrieve = MagicMock(return_value=mock_response)

            result = query_knowledge_base(query)
            parsed = json.loads(result)

        # Must not be an error
        assert "error_type" not in parsed

        passages = parsed["passages"]

        # All returned passages must have relevance_score >= threshold
        for i, passage in enumerate(passages):
            assert passage["relevance_score"] >= RELEVANCE_THRESHOLD, (
                f"Passage {i} has relevance_score {passage['relevance_score']} "
                f"below threshold {RELEVANCE_THRESHOLD}"
            )

        # If no passages meet threshold, must have explanatory message
        any_above_threshold = any(s >= RELEVANCE_THRESHOLD for s in scores)
        if not any_above_threshold:
            assert len(passages) == 0, (
                f"Expected empty passage list when no scores meet threshold, "
                f"got {len(passages)} passages"
            )
            assert parsed["message"] is not None, (
                "Expected explanatory message when no passages meet threshold"
            )
            assert isinstance(parsed["message"], str)
            assert len(parsed["message"]) > 0


class TestKnowledgeBaseQueryValidation:
    """Feature: bedrock-agentcore-demo, Property 8: Knowledge base query validation"""

    @given(query=empty_query_strategy)
    @settings(max_examples=100, deadline=None)
    def test_empty_query_returns_structured_error(self, query):
        """Feature: bedrock-agentcore-demo, Property 8: Knowledge base query validation

        For any query string that is empty or whitespace-only, the Knowledge_Base_MCP
        SHALL return a structured error indicating the query is invalid, without
        attempting a knowledge base lookup.

        Validates: Requirements 4.7
        """
        with patch(
            "mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client"
        ) as mock_client:
            result = query_knowledge_base(query)
            parsed = json.loads(result)

            # Must return structured error
            assert "error_type" in parsed, (
                f"Expected error response for empty/whitespace query '{repr(query)}', "
                f"got: {parsed}"
            )
            assert parsed["error_type"] == "INVALID_QUERY"
            assert "message" in parsed
            assert isinstance(parsed["message"], str)
            assert len(parsed["message"]) > 0

            # Must NOT have called the Bedrock client (no lookup performed)
            mock_client.assert_not_called()

    @given(query=oversized_query_strategy)
    @settings(max_examples=100, deadline=None)
    def test_oversized_query_returns_structured_error(self, query):
        """Feature: bedrock-agentcore-demo, Property 8: Knowledge base query validation

        For any query string that exceeds 1000 characters, the Knowledge_Base_MCP
        SHALL return a structured error indicating the query is invalid, without
        attempting a knowledge base lookup.

        Validates: Requirements 4.7
        """
        with patch(
            "mcp_servers.knowledge_base.server._get_bedrock_agent_runtime_client"
        ) as mock_client:
            result = query_knowledge_base(query)
            parsed = json.loads(result)

            # Must return structured error
            assert "error_type" in parsed, (
                f"Expected error response for query of length {len(query)}, "
                f"got: {parsed}"
            )
            assert parsed["error_type"] == "INVALID_QUERY"
            assert "message" in parsed
            assert isinstance(parsed["message"], str)
            assert len(parsed["message"]) > 0

            # Must NOT have called the Bedrock client (no lookup performed)
            mock_client.assert_not_called()
