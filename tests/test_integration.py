"""Integration tests for the Bedrock AgentCore Demo application.

Tests full request paths (API endpoint → service logic → data store) using:
- moto for DynamoDB and Cognito mocking
- unittest.mock to mock the Bedrock model/agent
- FastAPI TestClient against the full app
- httpx.AsyncClient with ASGI transport for MCP server health endpoints

Validates: Requirements 1.2, 2.1, 5.1, 8.3, 10.1
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from agent.runtime import AgentResponse, ToolInvocationDetail
from backend.api import app
from backend.db.dynamodb import DynamoDBClient, create_table
from backend.middleware.auth import CurrentUser, get_current_user

# Ensure test environment variables are set
os.environ.setdefault("COGNITO_USER_POOL_ID", "us-east-1_testpool")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cognito_env():
    """Set up a mocked Cognito user pool with a client for integration testing."""
    with mock_aws():
        client = boto3.client("cognito-idp", region_name="us-east-1")

        # Create user pool with password policy
        pool_response = client.create_user_pool(
            PoolName="integration-test-pool",
            Policies={
                "PasswordPolicy": {
                    "MinimumLength": 8,
                    "RequireUppercase": True,
                    "RequireLowercase": True,
                    "RequireNumbers": True,
                    "RequireSymbols": True,
                }
            },
            Schema=[
                {"Name": "email", "AttributeDataType": "String", "Required": True},
                {"Name": "display_name", "AttributeDataType": "String", "Mutable": True},
            ],
            AutoVerifiedAttributes=["email"],
        )
        pool_id = pool_response["UserPool"]["Id"]

        # Create user pool client with password auth flow
        client_response = client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName="integration-test-client",
            ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        )
        client_id = client_response["UserPoolClient"]["ClientId"]

        with patch.dict(
            os.environ,
            {"COGNITO_USER_POOL_ID": pool_id, "COGNITO_CLIENT_ID": client_id},
        ):
            with patch("backend.api.auth.COGNITO_USER_POOL_ID", pool_id):
                with patch("backend.api.auth.COGNITO_CLIENT_ID", client_id):
                    yield {
                        "pool_id": pool_id,
                        "client_id": client_id,
                        "cognito_client": client,
                    }


@pytest.fixture
def dynamodb_env():
    """Set up a mocked DynamoDB table for integration testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        create_table(dynamodb_resource=dynamodb)
        with patch("backend.api.chat._get_db_client") as mock_get_db:
            db_client = DynamoDBClient(endpoint_url=None)
            # The moto mock intercepts boto3 calls, so the default client works
            mock_get_db.return_value = db_client
            yield db_client


@pytest.fixture
def full_env(cognito_env, dynamodb_env):
    """Combined Cognito + DynamoDB mock environment for full integration tests."""
    yield {
        "cognito": cognito_env,
        "db": dynamodb_env,
    }


@pytest.fixture
def integration_client():
    """Create a TestClient for the full FastAPI app (no auth override)."""
    return TestClient(app)


@pytest.fixture
def authed_client(dynamodb_env):
    """Create a TestClient with authentication bypassed for chat/conversation tests."""
    test_user = CurrentUser(user_id="integration-user-001", email="student@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Integration Test: Registration and Sign-In Flow
# ---------------------------------------------------------------------------


class TestRegistrationAndSignInFlow:
    """Test the full registration → verification → sign-in flow against mocked Cognito.

    Validates: Requirement 1.2 (registration with valid inputs creates account),
               Requirement 2.1 (valid credentials authenticate and issue token).
    """

    def test_full_registration_and_signin(self, integration_client, cognito_env):
        """Register a user, confirm them, and sign in — full happy path."""
        email = "newstudent@example.com"
        password = "SecurePass1!"
        display_name = "New Student"

        # Step 1: Register
        register_resp = integration_client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": display_name},
        )
        assert register_resp.status_code == 200
        assert register_resp.json()["email"] == email

        # Step 2: Confirm the user (simulating email verification)
        cognito_env["cognito_client"].admin_confirm_sign_up(
            UserPoolId=cognito_env["pool_id"],
            Username=email,
        )

        # Step 3: Sign in
        signin_resp = integration_client.post(
            "/api/auth/signin",
            json={"email": email, "password": password},
        )
        assert signin_resp.status_code == 200
        data = signin_resp.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600

    def test_registration_then_duplicate_rejected(self, integration_client, cognito_env):
        """Registering the same email twice fails with duplicate error."""
        email = "duplicate@example.com"
        payload = {"email": email, "password": "ValidPass1!", "display_name": "User"}

        # First registration succeeds
        resp1 = integration_client.post("/api/auth/register", json=payload)
        assert resp1.status_code == 200

        # Second registration fails
        resp2 = integration_client.post("/api/auth/register", json=payload)
        assert resp2.status_code == 400
        assert resp2.json()["detail"]["error"] == "duplicate_email"

    def test_signin_with_wrong_password(self, integration_client, cognito_env):
        """Sign-in with incorrect password returns generic invalid_credentials error."""
        from backend.api.auth import _failed_attempts

        _failed_attempts.clear()

        email = "wrongpw@example.com"
        # Register and confirm
        integration_client.post(
            "/api/auth/register",
            json={"email": email, "password": "CorrectPass1!", "display_name": "User"},
        )
        cognito_env["cognito_client"].admin_confirm_sign_up(
            UserPoolId=cognito_env["pool_id"],
            Username=email,
        )

        # Attempt sign-in with wrong password
        resp = integration_client.post(
            "/api/auth/signin",
            json={"email": email, "password": "WrongPass1!"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_credentials"

    def test_signin_lockout_after_failed_attempts(self, integration_client, cognito_env):
        """Account gets locked after 5 consecutive failed sign-in attempts."""
        from backend.api.auth import _failed_attempts

        _failed_attempts.clear()

        email = "lockme@example.com"
        integration_client.post(
            "/api/auth/register",
            json={"email": email, "password": "CorrectPass1!", "display_name": "Lock User"},
        )
        cognito_env["cognito_client"].admin_confirm_sign_up(
            UserPoolId=cognito_env["pool_id"],
            Username=email,
        )

        # 5 failed attempts
        for _ in range(5):
            integration_client.post(
                "/api/auth/signin",
                json={"email": email, "password": "BadPassword1!"},
            )

        # 6th attempt triggers lockout
        resp = integration_client.post(
            "/api/auth/signin",
            json={"email": email, "password": "CorrectPass1!"},
        )
        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "account_locked"


# ---------------------------------------------------------------------------
# Integration Test: Chat Message Flow
# ---------------------------------------------------------------------------


class TestChatMessageFlow:
    """Test the full chat message flow from API through agent (mocked Bedrock).

    Validates: Requirement 5.1 (student sends message, agent processes and responds).
    """

    @patch("backend.api.chat.process_message")
    @patch("backend.api.chat.create_agent")
    def test_send_message_creates_conversation_and_persists(
        self, mock_create_agent, mock_process, authed_client
    ):
        """Sending a message with no conversation_id creates one and persists messages."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="I can help with that. The current stock price of AAPL is $175.50.",
            tool_invocations=[
                ToolInvocationDetail(
                    mcp_server="financial-research",
                    tool_name="get_stock_quote",
                    status="succeeded",
                    duration_ms=320.5,
                ),
            ],
            timed_out=False,
        )

        # Send message
        resp = authed_client.post(
            "/api/chat/message",
            json={"message": "What is the current AAPL stock price?"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["role"] == "assistant"
        assert "175.50" in data["content"]
        assert data["conversation_id"] is not None
        assert len(data["tool_invocations"]) == 1
        assert data["tool_invocations"][0]["mcp_server"] == "financial-research"
        assert data["tool_invocations"][0]["tool_name"] == "get_stock_quote"
        assert data["tool_invocations"][0]["status"] == "succeeded"

    @patch("backend.api.chat.process_message")
    @patch("backend.api.chat.create_agent")
    def test_send_message_to_existing_conversation(
        self, mock_create_agent, mock_process, authed_client
    ):
        """Sending a message with existing conversation_id doesn't create a new one."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="First response",
            tool_invocations=[],
            timed_out=False,
        )

        # First message creates conversation
        resp1 = authed_client.post(
            "/api/chat/message",
            json={"message": "Hello"},
        )
        assert resp1.status_code == 200
        conv_id = resp1.json()["conversation_id"]

        # Second message to same conversation
        mock_process.return_value = AgentResponse(
            text="Second response",
            tool_invocations=[],
            timed_out=False,
        )

        resp2 = authed_client.post(
            "/api/chat/message",
            json={"message": "Follow up question", "conversation_id": conv_id},
        )
        assert resp2.status_code == 200
        assert resp2.json()["conversation_id"] == conv_id

    @patch("backend.api.chat.process_message")
    @patch("backend.api.chat.create_agent")
    def test_agent_timeout_handled_gracefully(
        self, mock_create_agent, mock_process, authed_client
    ):
        """Agent timeout returns a timeout message instead of an error."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="Request timed out. The agent could not complete processing within 30 seconds.",
            tool_invocations=[],
            timed_out=True,
        )

        resp = authed_client.post(
            "/api/chat/message",
            json={"message": "Very complex multi-step question"},
        )
        assert resp.status_code == 200
        assert "timed out" in resp.json()["content"].lower()

    @patch("backend.api.chat.process_message")
    @patch("backend.api.chat.create_agent")
    def test_agent_error_returns_500(
        self, mock_create_agent, mock_process, authed_client
    ):
        """When agent raises an exception, returns 500 internal error."""
        mock_create_agent.side_effect = Exception("Bedrock connection failed")

        resp = authed_client.post(
            "/api/chat/message",
            json={"message": "Hello"},
        )
        assert resp.status_code == 500
        assert resp.json()["detail"]["error"] == "internal_error"

    def test_message_validation_empty(self, authed_client):
        """Empty message is rejected at the API level."""
        resp = authed_client.post("/api/chat/message", json={"message": ""})
        assert resp.status_code == 422

    def test_message_validation_too_long(self, authed_client):
        """Message over 2000 characters is rejected at the API level."""
        resp = authed_client.post(
            "/api/chat/message", json={"message": "x" * 2001}
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Integration Test: Conversation CRUD Operations
# ---------------------------------------------------------------------------


class TestConversationCRUD:
    """Test conversation CRUD operations against mocked DynamoDB.

    Validates: Requirement 10.1 (messages persisted in chronological order).
    """

    def test_create_conversation(self, authed_client):
        """Creating a conversation returns the conversation metadata."""
        resp = authed_client.post(
            "/api/chat/conversations",
            json={"title": "Financial Research Session"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Financial Research Session"
        assert "conversation_id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_list_conversations_empty(self, authed_client):
        """Listing conversations for a new user returns empty list."""
        resp = authed_client.get("/api/chat/conversations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_conversations_after_creating(self, authed_client):
        """Conversations appear in the list after creation."""
        # Create two conversations
        authed_client.post(
            "/api/chat/conversations",
            json={"title": "First Conversation"},
        )
        authed_client.post(
            "/api/chat/conversations",
            json={"title": "Second Conversation"},
        )

        resp = authed_client.get("/api/chat/conversations")
        assert resp.status_code == 200
        conversations = resp.json()
        assert len(conversations) == 2
        # Should be ordered by most recent activity
        titles = [c["title"] for c in conversations]
        assert "First Conversation" in titles
        assert "Second Conversation" in titles

    @patch("backend.api.chat.process_message")
    @patch("backend.api.chat.create_agent")
    def test_get_conversation_messages_in_order(
        self, mock_create_agent, mock_process, authed_client
    ):
        """Messages are returned in chronological order for a conversation."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="Response 1",
            tool_invocations=[],
            timed_out=False,
        )

        # Send first message
        resp1 = authed_client.post(
            "/api/chat/message",
            json={"message": "First question"},
        )
        conv_id = resp1.json()["conversation_id"]

        # Send second message
        mock_process.return_value = AgentResponse(
            text="Response 2",
            tool_invocations=[],
            timed_out=False,
        )
        authed_client.post(
            "/api/chat/message",
            json={"message": "Second question", "conversation_id": conv_id},
        )

        # Retrieve messages
        resp = authed_client.get(f"/api/chat/conversations/{conv_id}")
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        assert len(messages) == 4  # 2 user + 2 assistant messages

        # Verify chronological order
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "user", "assistant"]
        assert messages[0]["content"] == "First question"
        assert messages[1]["content"] == "Response 1"
        assert messages[2]["content"] == "Second question"
        assert messages[3]["content"] == "Response 2"

    def test_get_conversation_messages_nonexistent(self, authed_client):
        """Getting messages for a non-existent conversation returns empty list."""
        resp = authed_client.get("/api/chat/conversations/nonexistent-id")
        assert resp.status_code == 200
        assert resp.json()["messages"] == []

    @patch("backend.api.chat.process_message")
    @patch("backend.api.chat.create_agent")
    def test_conversation_appears_in_list_after_message(
        self, mock_create_agent, mock_process, authed_client
    ):
        """A conversation created by sending a message appears in the list."""
        mock_agent = MagicMock()
        mock_create_agent.return_value = mock_agent

        mock_process.return_value = AgentResponse(
            text="Hello!",
            tool_invocations=[],
            timed_out=False,
        )

        authed_client.post(
            "/api/chat/message",
            json={"message": "Tell me about AWS"},
        )

        resp = authed_client.get("/api/chat/conversations")
        assert resp.status_code == 200
        conversations = resp.json()
        assert len(conversations) >= 1
        # Title is auto-generated from first message
        assert any("Tell me about AWS" in c["title"] for c in conversations)


# ---------------------------------------------------------------------------
# Integration Test: MCP Server Health Endpoints
# ---------------------------------------------------------------------------


class TestMCPServerHealth:
    """Test MCP server health endpoints via ASGI transport.

    Validates: Requirement 8.3 (services accept connections on configured ports).
    """

    @pytest.mark.asyncio
    async def test_financial_research_mcp_health(self):
        """Financial Research MCP server health endpoint returns healthy status."""
        from mcp_servers.financial_research.server import mcp as financial_mcp

        # Get the underlying Starlette/ASGI app from FastMCP
        # FastMCP exposes a streamable HTTP app via streamable_http_app()
        starlette_app = financial_mcp.streamable_http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=starlette_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "financial-research-mcp"

    @pytest.mark.asyncio
    async def test_knowledge_base_mcp_health(self):
        """Knowledge Base MCP server health endpoint returns healthy status."""
        from mcp_servers.knowledge_base.server import mcp as kb_mcp

        starlette_app = kb_mcp.streamable_http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=starlette_app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "knowledge-base-mcp"


# ---------------------------------------------------------------------------
# Integration Test: Backend API Health and Service Startup
# ---------------------------------------------------------------------------


class TestServiceStartup:
    """Test service startup sequence and health checks.

    Validates: Requirement 8.3 (services start and accept connections).
    """

    def test_backend_api_health(self, integration_client):
        """Backend API health endpoint returns healthy status."""
        resp = integration_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "backend-api"

    def test_api_routes_registered(self, integration_client):
        """All expected API routes are registered on the app."""
        # Use OpenAPI schema to enumerate all registered paths reliably,
        # since FastAPI's app.routes includes _IncludedRouter objects that
        # don't expose a direct .path attribute.
        schema = app.openapi()
        routes = list(schema.get("paths", {}).keys())
        assert "/health" in routes
        assert "/api/auth/register" in routes
        assert "/api/auth/verify" in routes
        assert "/api/auth/signin" in routes
        assert "/api/auth/signout" in routes
        assert "/api/chat/message" in routes
        assert "/api/chat/conversations" in routes
        assert "/api/chat/conversations/{conversation_id}" in routes

    def test_unauthenticated_chat_rejected(self, integration_client):
        """Chat endpoints reject unauthenticated requests."""
        resp = integration_client.post(
            "/api/chat/message",
            json={"message": "Hello"},
        )
        # Should be 401 or 403 — depends on implementation
        assert resp.status_code in (401, 403)

    def test_unauthenticated_conversations_rejected(self, integration_client):
        """Conversation list endpoint rejects unauthenticated requests."""
        resp = integration_client.get("/api/chat/conversations")
        assert resp.status_code in (401, 403)
