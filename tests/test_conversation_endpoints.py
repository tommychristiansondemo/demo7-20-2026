"""Unit tests for the conversation management endpoints.

Tests the GET /api/chat/conversations, GET /api/chat/conversations/{id},
POST /api/chat/conversations, and GET /api/chat/trace/{request_id} endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.chat import router
from backend.middleware.auth import CurrentUser, get_current_user


# --- Test Setup ---


def _create_test_app() -> FastAPI:
    """Create a FastAPI app with the chat router for testing."""
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_current_user():
    """Create a mock authenticated user."""
    return CurrentUser(user_id="user-123", email="test@example.com")


app = _create_test_app()


@pytest.fixture
def client():
    """Create a test client with mocked auth."""
    app.dependency_overrides[get_current_user] = lambda: _mock_current_user()
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- List Conversations Tests ---


class TestListConversations:
    """Tests for GET /api/chat/conversations."""

    @patch("backend.api.chat._get_db_client")
    def test_returns_conversations_list(self, mock_db_client, client):
        """Should return a list of conversations for the authenticated user."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.get_conversations.return_value = [
            {
                "conversation_id": "conv-1",
                "title": "First conversation",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T01:00:00+00:00",
            },
            {
                "conversation_id": "conv-2",
                "title": "Second conversation",
                "created_at": "2024-01-02T00:00:00+00:00",
                "updated_at": "2024-01-02T01:00:00+00:00",
            },
        ]

        response = client.get("/api/chat/conversations")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["conversation_id"] == "conv-1"
        assert data[0]["title"] == "First conversation"
        assert data[1]["conversation_id"] == "conv-2"

        # Verify called with correct user_id and limit
        mock_db.get_conversations.assert_called_once_with(user_id="user-123", limit=50)

    @patch("backend.api.chat._get_db_client")
    def test_returns_empty_list_when_no_conversations(self, mock_db_client, client):
        """Should return empty list when user has no conversations."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.get_conversations.return_value = []

        response = client.get("/api/chat/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @patch("backend.api.chat._get_db_client")
    def test_handles_db_error(self, mock_db_client, client):
        """Should return 500 when DynamoDB fails."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.get_conversations.side_effect = Exception("DynamoDB error")

        response = client.get("/api/chat/conversations")

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "internal_error"


# --- Get Conversation Messages Tests ---


class TestGetConversationMessages:
    """Tests for GET /api/chat/conversations/{id}."""

    @patch("backend.api.chat._get_db_client")
    def test_returns_messages_in_order(self, mock_db_client, client):
        """Should return messages for a conversation in chronological order."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.get_messages.return_value = [
            {
                "conversation_id": "conv-1",
                "message_id": "msg-1",
                "role": "user",
                "content": "Hello",
                "timestamp": "2024-01-01T00:00:00+00:00",
                "tool_invocations": [],
                "trace": None,
            },
            {
                "conversation_id": "conv-1",
                "message_id": "msg-2",
                "role": "assistant",
                "content": "Hi there!",
                "timestamp": "2024-01-01T00:00:01+00:00",
                "tool_invocations": [],
                "trace": None,
            },
        ]

        response = client.get("/api/chat/conversations/conv-1")

        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == "conv-1"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "Hello"
        assert data["messages"][1]["role"] == "assistant"
        assert data["messages"][1]["content"] == "Hi there!"

        mock_db.get_messages.assert_called_once_with(
            user_id="user-123", conversation_id="conv-1"
        )

    @patch("backend.api.chat._get_db_client")
    def test_returns_empty_messages_for_new_conversation(self, mock_db_client, client):
        """Should return empty message list for a conversation with no messages."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.get_messages.return_value = []

        response = client.get("/api/chat/conversations/conv-new")

        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == "conv-new"
        assert data["messages"] == []

    @patch("backend.api.chat._get_db_client")
    def test_handles_db_error(self, mock_db_client, client):
        """Should return 500 when DynamoDB fails."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.get_messages.side_effect = Exception("DynamoDB error")

        response = client.get("/api/chat/conversations/conv-1")

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "internal_error"


# --- Create Conversation Tests ---


class TestCreateConversation:
    """Tests for POST /api/chat/conversations."""

    @patch("backend.api.chat._get_db_client")
    def test_creates_conversation_successfully(self, mock_db_client, client):
        """Should create a new conversation and return it."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.create_conversation.return_value = {
            "user_id": "user-123",
            "conversation_id": "new-conv-id",
            "title": "New Chat",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }

        response = client.post(
            "/api/chat/conversations",
            json={"title": "New Chat"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Chat"
        assert data["conversation_id"] == "new-conv-id"
        assert "created_at" in data
        assert "updated_at" in data

        mock_db.create_conversation.assert_called_once()
        call_kwargs = mock_db.create_conversation.call_args.kwargs
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["title"] == "New Chat"

    def test_rejects_empty_title(self, client):
        """Should reject request with empty title."""
        response = client.post(
            "/api/chat/conversations",
            json={"title": ""},
        )
        assert response.status_code == 422

    def test_rejects_missing_title(self, client):
        """Should reject request without title field."""
        response = client.post(
            "/api/chat/conversations",
            json={},
        )
        assert response.status_code == 422

    @patch("backend.api.chat._get_db_client")
    def test_handles_db_error(self, mock_db_client, client):
        """Should return 500 when DynamoDB fails."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db
        mock_db.create_conversation.side_effect = Exception("DynamoDB error")

        response = client.post(
            "/api/chat/conversations",
            json={"title": "New Chat"},
        )

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "internal_error"


# --- Get Trace Tests ---


class TestGetTrace:
    """Tests for GET /api/chat/trace/{request_id}."""

    @patch("backend.api.chat._get_db_client")
    def test_returns_trace_data(self, mock_db_client, client):
        """Should return trace data for a valid request_id."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_table = MagicMock()
        mock_db._table = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "PK": "USER#user-123",
                "SK": "MSG#req-123",
                "data": {
                    "trace": {
                        "total_latency_ms": 1500,
                        "tool_call_count": 2,
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "spans": [],
                    },
                    "tool_invocations": [
                        {
                            "mcp_server": "financial-research",
                            "tool_name": "get_stock_quote",
                            "status": "succeeded",
                            "duration_ms": 250,
                        }
                    ],
                },
            }
        }

        response = client.get("/api/chat/trace/req-123")

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "req-123"
        assert data["trace"]["total_latency_ms"] == 1500
        assert data["trace"]["tool_call_count"] == 2
        assert len(data["tool_invocations"]) == 1
        assert data["tool_invocations"][0]["mcp_server"] == "financial-research"

    @patch("backend.api.chat._get_db_client")
    def test_returns_404_when_not_found(self, mock_db_client, client):
        """Should return 404 when trace data doesn't exist."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_table = MagicMock()
        mock_db._table = mock_table
        mock_table.get_item.return_value = {}

        response = client.get("/api/chat/trace/nonexistent-id")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "not_found"

    @patch("backend.api.chat._get_db_client")
    def test_returns_null_trace_when_no_trace_data(self, mock_db_client, client):
        """Should return null trace when message exists but has no trace."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_table = MagicMock()
        mock_db._table = mock_table
        mock_table.get_item.return_value = {
            "Item": {
                "PK": "USER#user-123",
                "SK": "MSG#req-456",
                "data": {
                    "tool_invocations": [],
                    "trace": None,
                },
            }
        }

        response = client.get("/api/chat/trace/req-456")

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "req-456"
        assert data["trace"] is None
        assert data["tool_invocations"] == []

    @patch("backend.api.chat._get_db_client")
    def test_handles_db_error(self, mock_db_client, client):
        """Should return 500 when DynamoDB fails."""
        mock_db = MagicMock()
        mock_db_client.return_value = mock_db

        mock_table = MagicMock()
        mock_db._table = mock_table
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        response = client.get("/api/chat/trace/req-123")

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "internal_error"
