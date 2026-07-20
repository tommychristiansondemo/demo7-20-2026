"""Property-based tests for chat message validation and tool invocation display.

Feature: bedrock-agentcore-demo, Property 11: Chat message length validation
Feature: bedrock-agentcore-demo, Property 10: Tool invocation display completeness

Validates: Requirements 5.4, 5.8
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agent.runtime import AgentResponse, ToolInvocationDetail
from backend.api.chat import router
from backend.middleware.auth import CurrentUser, get_current_user


# --- Test Setup ---


def _mock_current_user():
    """Create a mock authenticated user."""
    return CurrentUser(user_id="user-prop-test", email="prop@example.com")


def _create_test_app() -> FastAPI:
    """Create a FastAPI app with the chat router for testing."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _mock_current_user()
    return app


app = _create_test_app()
client = TestClient(app)


# --- Strategies ---


def empty_message_strategy():
    """Generate empty messages (zero-length strings)."""
    return st.just("")


def too_long_message_strategy():
    """Generate messages that exceed 2000 characters."""
    return st.integers(min_value=2001, max_value=3000).flatmap(
        lambda n: st.text(
            alphabet=st.characters(categories=("L", "N", "P", "Z")),
            min_size=n,
            max_size=n,
        )
    )


def invalid_message_strategy():
    """Generate messages that are either empty or exceed 2000 characters."""
    return st.one_of(
        empty_message_strategy(),
        too_long_message_strategy(),
    )


def mcp_server_name_strategy():
    """Generate valid MCP server names."""
    return st.one_of(
        st.just("financial-research"),
        st.just("knowledge-base"),
        st.text(
            alphabet=st.characters(categories=("L",), whitelist_categories=("Ll",)),
            min_size=3,
            max_size=30,
        ).map(lambda s: s.lower().replace(" ", "-")),
    )


def tool_name_strategy():
    """Generate valid tool names."""
    return st.one_of(
        st.just("get_stock_quote"),
        st.just("get_company_profile"),
        st.just("get_market_summary"),
        st.just("query_knowledge_base"),
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz_",
            min_size=3,
            max_size=40,
        ),
    )


def tool_status_strategy():
    """Generate valid tool invocation statuses."""
    return st.sampled_from(["pending", "succeeded", "failed"])


def tool_invocation_strategy():
    """Generate a ToolInvocationDetail with random but valid fields."""
    return st.builds(
        ToolInvocationDetail,
        mcp_server=mcp_server_name_strategy(),
        tool_name=tool_name_strategy(),
        status=tool_status_strategy(),
        duration_ms=st.floats(min_value=0.1, max_value=30000.0, allow_nan=False, allow_infinity=False),
    )


# --- Property Tests ---


class TestChatMessageLengthValidation:
    """Feature: bedrock-agentcore-demo, Property 11: Chat message length validation"""

    @given(message=empty_message_strategy())
    @settings(max_examples=100, deadline=None)
    def test_empty_message_rejected(self, message):
        """Feature: bedrock-agentcore-demo, Property 11: Chat message length validation

        For any empty message (0 characters), the system rejects the submission
        and displays a validation message indicating the allowed message length.

        Validates: Requirements 5.8
        """
        response = client.post(
            "/api/chat/message",
            json={"message": message},
        )
        # Pydantic validation rejects empty messages with 422
        assert response.status_code == 422, (
            f"Expected 422 for empty message, got {response.status_code}"
        )
        data = response.json()
        assert "detail" in data

    @given(message=too_long_message_strategy())
    @settings(max_examples=100, deadline=None)
    def test_too_long_message_rejected(self, message):
        """Feature: bedrock-agentcore-demo, Property 11: Chat message length validation

        For any message exceeding 2000 characters, the system rejects the submission
        and displays a validation message indicating the allowed message length.

        Validates: Requirements 5.8
        """
        assume(len(message) > 2000)

        response = client.post(
            "/api/chat/message",
            json={"message": message},
        )
        # Pydantic validation rejects oversized messages with 422
        assert response.status_code == 422, (
            f"Expected 422 for message of length {len(message)}, got {response.status_code}"
        )
        data = response.json()
        assert "detail" in data


class TestToolInvocationDisplayCompleteness:
    """Feature: bedrock-agentcore-demo, Property 10: Tool invocation display completeness"""

    @given(invocations=st.lists(tool_invocation_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_tool_invocations_include_all_fields(self, invocations):
        """Feature: bedrock-agentcore-demo, Property 10: Tool invocation display completeness

        For any tool invocation (successful or failed) made by the Agent, the system
        presents to the student the MCP server name, the tool name, and the invocation
        status (pending, succeeded, or failed).

        Validates: Requirements 5.4
        """
        with patch("backend.api.chat._get_db_client") as mock_db_client, \
             patch("backend.api.chat.create_agent") as mock_create_agent, \
             patch("backend.api.chat.process_message") as mock_process:

            mock_db = MagicMock()
            mock_db_client.return_value = mock_db

            mock_agent = MagicMock()
            mock_create_agent.return_value = mock_agent

            mock_process.return_value = AgentResponse(
                text="Agent response with tools",
                tool_invocations=invocations,
                timed_out=False,
            )

            response = client.post(
                "/api/chat/message",
                json={"message": "Test message for tool invocations"},
            )

            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )
            data = response.json()

            # Verify the response includes tool_invocations array
            assert "tool_invocations" in data
            response_invocations = data["tool_invocations"]

            # Verify count matches
            assert len(response_invocations) == len(invocations), (
                f"Expected {len(invocations)} tool invocations, "
                f"got {len(response_invocations)}"
            )

            # For each tool invocation, verify all required fields are present
            for i, inv_response in enumerate(response_invocations):
                original = invocations[i]

                # MCP server name must be present and match
                assert "mcp_server" in inv_response, (
                    f"Tool invocation {i} missing 'mcp_server' field"
                )
                assert inv_response["mcp_server"] == original.mcp_server, (
                    f"Tool invocation {i} mcp_server mismatch: "
                    f"expected '{original.mcp_server}', got '{inv_response['mcp_server']}'"
                )

                # Tool name must be present and match
                assert "tool_name" in inv_response, (
                    f"Tool invocation {i} missing 'tool_name' field"
                )
                assert inv_response["tool_name"] == original.tool_name, (
                    f"Tool invocation {i} tool_name mismatch: "
                    f"expected '{original.tool_name}', got '{inv_response['tool_name']}'"
                )

                # Status must be present and match
                assert "status" in inv_response, (
                    f"Tool invocation {i} missing 'status' field"
                )
                assert inv_response["status"] == original.status, (
                    f"Tool invocation {i} status mismatch: "
                    f"expected '{original.status}', got '{inv_response['status']}'"
                )
