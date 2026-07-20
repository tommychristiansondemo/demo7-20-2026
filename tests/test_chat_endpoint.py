"""Unit tests for the chat message endpoint.

Tests the POST /api/chat/message endpoint with mocked agent and DynamoDB.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.runtime import AgentResponse, ToolInvocationDetail
from backend.api.chat import router, _generate_id
from backend.middleware.auth import CurrentUser


# --- Test Setup ---


def _create_test_app() -> FastAPI:
    """Create a FastAPI app with the chat router for testing."""
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_current_user():
    """Create a mock authenticated user."""
    return CurrentUser(user_id="user-123", email="test@example.com")


# Override the auth dependency globally for the test app
app = _create_test_app()


@pytest.fixture
def client():
    """Create a test client with mocked auth."""
    from backend.middleware.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _mock_current_user()
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Tests ---


class TestMessageValidation:
    """Tests for message validation."""

    def test_empty_message_rejected(self, client):
        """Empty message should be rejected with 422 validation error."""
        response = client.post("/api/chat/message", json={"message": ""})
        assert response.status_code == 422

    def test_message_too_long_rejected(self, client):
        """Message over 2000 chars should be rejected with 422 validation error."""
        long_message = "a" * 2001
        response = client.post("/api/chat/message", json={"message": long_message})
        assert response.status_code == 422

    def test_missing_message_rejected(self, client):
        """Missing message field should be rejected."""
        response = client.post("/api/chat/message", json={})
        assert response.status_code == 422


class TestSuccessfulMessage:
    """Tests for successful message processing."""

    @patch("backend.api.chat._get_db_client")
    @patch("backend.api.chat.create_agent")
    @patch("backend.api.chat.process_message")
    def test_new_conversation_created(self, mock_process, mock_create_agent, mock_db_client, client):
        """When no conversation_id provided, a new conversation is created."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="Hello! How can I help?",
            tool_invocations=[],
            timed_out=False,
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "Hello"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "assistant"
        assert data["content"] == "Hello! How can I help?"
        assert data["conversation_id"] is not None
        assert data["message_id"] is not None
        assert data["tool_invocations"] == []

        # Verify conversation was created
        mock_db.create_conversation.assert_called_once()

        # Verify both user and assistant messages were persisted
        assert mock_db.add_message.call_count == 2
        user_call = mock_db.add_message.call_args_list[0]
        assert user_call.kwargs["role"] == "user"
        assert user_call.kwargs["content"] == "Hello"

        assistant_call = mock_db.add_message.call_args_list[1]
        assert assistant_call.kwargs["role"] == "assistant"
        assert assistant_call.kwargs["content"] == "Hello! How can I help?"

    @patch("backend.api.chat._get_db_client")
    @patch("backend.api.chat.create_agent")
    @patch("backend.api.chat.process_message")
    def test_existing_conversation_used(self, mock_process, mock_create_agent, mock_db_client, client):
        """When conversation_id provided, no new conversation is created."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="Response text",
            tool_invocations=[],
            timed_out=False,
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "Hello", "conversation_id": "existing-conv-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == "existing-conv-123"

        # Verify no new conversation was created
        mock_db.create_conversation.assert_not_called()

    @patch("backend.api.chat._get_db_client")
    @patch("backend.api.chat.create_agent")
    @patch("backend.api.chat.process_message")
    def test_tool_invocations_included(self, mock_process, mock_create_agent, mock_db_client, client):
        """Tool invocation details are included in the response."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="The stock price is $150.",
            tool_invocations=[
                ToolInvocationDetail(
                    mcp_server="financial-research",
                    tool_name="get_stock_quote",
                    status="succeeded",
                    duration_ms=250.0,
                ),
            ],
            timed_out=False,
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "What is AAPL stock price?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tool_invocations"]) == 1
        tool = data["tool_invocations"][0]
        assert tool["mcp_server"] == "financial-research"
        assert tool["tool_name"] == "get_stock_quote"
        assert tool["status"] == "succeeded"
        assert tool["duration_ms"] == 250.0


class TestTimeoutHandling:
    """Tests for agent timeout handling."""

    @patch("backend.api.chat._get_db_client")
    @patch("backend.api.chat.create_agent")
    @patch("backend.api.chat.process_message")
    def test_timeout_returns_timeout_message(self, mock_process, mock_create_agent, mock_db_client, client):
        """When agent times out, response contains timeout message."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="Request timed out. The agent could not complete processing within 30 seconds. Please try a simpler question or try again later.",
            tool_invocations=[],
            timed_out=True,
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "Complex question here"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "timed out" in data["content"].lower()
        assert data["tool_invocations"] == []


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @patch("backend.api.chat._get_db_client")
    @patch("backend.api.chat.create_agent")
    @patch("backend.api.chat.process_message")
    def test_agent_error_returns_error_message(self, mock_process, mock_create_agent, mock_db_client, client):
        """When agent encounters an MCP error, response includes error details."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="An error occurred while processing your request: Financial Research MCP server tool get_stock_quote failed",
            tool_invocations=[
                ToolInvocationDetail(
                    mcp_server="financial-research",
                    tool_name="get_stock_quote",
                    status="failed",
                    duration_ms=100.0,
                ),
            ],
            timed_out=False,
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "Get stock for INVALID"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tool_invocations"][0]["status"] == "failed"
        assert data["tool_invocations"][0]["mcp_server"] == "financial-research"

    @patch("backend.api.chat._get_db_client")
    @patch("backend.api.chat.create_agent")
    @patch("backend.api.chat.process_message")
    def test_agent_creation_failure(self, mock_process, mock_create_agent, mock_db_client, client):
        """When agent fails to be created, returns 500 error."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_create_agent.side_effect = Exception("Connection refused")

        response = client.post(
            "/api/chat/message",
            json={"message": "Hello"},
        )

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "internal_error"


class TestMessagePersistence:
    """Tests for message persistence behavior."""

    @patch("backend.api.chat._get_db_client")
    @patch("backend.api.chat.create_agent")
    @patch("backend.api.chat.process_message")
    def test_messages_persisted_with_tool_invocations(self, mock_process, mock_create_agent, mock_db_client, client):
        """Assistant message is persisted with tool invocation details."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="Result from tool",
            tool_invocations=[
                ToolInvocationDetail(
                    mcp_server="knowledge-base",
                    tool_name="query_knowledge_base",
                    status="succeeded",
                    duration_ms=500.0,
                ),
            ],
            timed_out=False,
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "What is AgentCore?"},
        )

        assert response.status_code == 200

        # Verify assistant message was persisted with tool invocations
        assistant_call = mock_db.add_message.call_args_list[1]
        assert assistant_call.kwargs["tool_invocations"] == [
            {
                "mcp_server": "knowledge-base",
                "tool_name": "query_knowledge_base",
                "status": "succeeded",
                "duration_ms": 500.0,
            }
        ]
