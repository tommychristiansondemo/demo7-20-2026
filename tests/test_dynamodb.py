"""Unit tests for the DynamoDB data access layer."""

from datetime import datetime, timezone, timedelta

import boto3
import pytest
from moto import mock_aws

from backend.db.dynamodb import DynamoDBClient, create_table, TABLE_NAME


@pytest.fixture
def dynamodb_table():
    """Create a mocked DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        create_table(dynamodb_resource=dynamodb)
        yield dynamodb


@pytest.fixture
def client(dynamodb_table):
    """Create a DynamoDBClient connected to the mocked table."""
    # Use the mocked resource's table directly
    db_client = DynamoDBClient.__new__(DynamoDBClient)
    db_client._table_name = TABLE_NAME
    db_client._dynamodb = dynamodb_table
    db_client._table = dynamodb_table.Table(TABLE_NAME)
    return db_client


class TestCreateConversation:
    """Tests for create_conversation method."""

    def test_creates_conversation_with_provided_timestamp(self, client):
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = client.create_conversation(
            user_id="user-123",
            conversation_id="conv-abc",
            title="Test Conversation",
            created_at=now,
        )

        assert result["user_id"] == "user-123"
        assert result["conversation_id"] == "conv-abc"
        assert result["title"] == "Test Conversation"
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()

    def test_creates_conversation_with_default_timestamp(self, client):
        result = client.create_conversation(
            user_id="user-123",
            conversation_id="conv-abc",
            title="Test Conversation",
        )

        assert result["user_id"] == "user-123"
        assert result["conversation_id"] == "conv-abc"
        assert "created_at" in result
        assert "updated_at" in result


class TestAddMessage:
    """Tests for add_message method."""

    def test_adds_message_to_conversation(self, client):
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-abc",
            title="Test",
            created_at=now,
        )

        msg_time = now + timedelta(seconds=30)
        result = client.add_message(
            user_id="user-123",
            conversation_id="conv-abc",
            message_id="msg-001",
            role="user",
            content="Hello, agent!",
            timestamp=msg_time,
        )

        assert result["conversation_id"] == "conv-abc"
        assert result["message_id"] == "msg-001"
        assert result["role"] == "user"
        assert result["content"] == "Hello, agent!"
        assert result["timestamp"] == msg_time.isoformat()
        assert result["tool_invocations"] == []
        assert result["trace"] is None

    def test_adds_message_with_tool_invocations(self, client):
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-abc",
            title="Test",
            created_at=now,
        )

        tool_invocations = [
            {
                "mcp_server": "financial-research",
                "tool_name": "get_stock_quote",
                "status": "succeeded",
                "duration_ms": 150.0,
                "input": {"ticker": "AAPL"},
                "output": {"price": 185.0},
            }
        ]

        result = client.add_message(
            user_id="user-123",
            conversation_id="conv-abc",
            message_id="msg-002",
            role="assistant",
            content="The current price of AAPL is $185.",
            timestamp=now + timedelta(seconds=60),
            tool_invocations=tool_invocations,
        )

        assert result["tool_invocations"] == tool_invocations


class TestGetConversations:
    """Tests for get_conversations method."""

    def test_returns_empty_list_for_new_user(self, client):
        result = client.get_conversations(user_id="user-new")
        assert result == []

    def test_returns_conversations_ordered_by_most_recent(self, client):
        base_time = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        # Create conversations at different times
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-old",
            title="Old Conversation",
            created_at=base_time,
        )
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-mid",
            title="Middle Conversation",
            created_at=base_time + timedelta(hours=1),
        )
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-new",
            title="New Conversation",
            created_at=base_time + timedelta(hours=2),
        )

        result = client.get_conversations(user_id="user-123")

        assert len(result) == 3
        # Most recent first
        assert result[0]["conversation_id"] == "conv-new"
        assert result[1]["conversation_id"] == "conv-mid"
        assert result[2]["conversation_id"] == "conv-old"

    def test_respects_limit_parameter(self, client):
        base_time = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        for i in range(5):
            client.create_conversation(
                user_id="user-123",
                conversation_id=f"conv-{i:03d}",
                title=f"Conversation {i}",
                created_at=base_time + timedelta(minutes=i),
            )

        result = client.get_conversations(user_id="user-123", limit=3)
        assert len(result) == 3

    def test_isolates_conversations_by_user(self, client):
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        client.create_conversation(
            user_id="user-alice",
            conversation_id="conv-alice",
            title="Alice's Chat",
            created_at=now,
        )
        client.create_conversation(
            user_id="user-bob",
            conversation_id="conv-bob",
            title="Bob's Chat",
            created_at=now,
        )

        alice_convs = client.get_conversations(user_id="user-alice")
        bob_convs = client.get_conversations(user_id="user-bob")

        assert len(alice_convs) == 1
        assert alice_convs[0]["conversation_id"] == "conv-alice"
        assert len(bob_convs) == 1
        assert bob_convs[0]["conversation_id"] == "conv-bob"


class TestGetMessages:
    """Tests for get_messages method."""

    def test_returns_empty_list_for_no_messages(self, client):
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-abc",
            title="Test",
            created_at=now,
        )

        result = client.get_messages(user_id="user-123", conversation_id="conv-abc")
        assert result == []

    def test_returns_messages_in_chronological_order(self, client):
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-abc",
            title="Test",
            created_at=now,
        )

        # Add messages in mixed order (but ULIDs would be sequential in practice)
        client.add_message(
            user_id="user-123",
            conversation_id="conv-abc",
            message_id="msg-001",
            role="user",
            content="First message",
            timestamp=now + timedelta(seconds=10),
        )
        client.add_message(
            user_id="user-123",
            conversation_id="conv-abc",
            message_id="msg-002",
            role="assistant",
            content="Second message",
            timestamp=now + timedelta(seconds=20),
        )
        client.add_message(
            user_id="user-123",
            conversation_id="conv-abc",
            message_id="msg-003",
            role="user",
            content="Third message",
            timestamp=now + timedelta(seconds=30),
        )

        result = client.get_messages(user_id="user-123", conversation_id="conv-abc")

        assert len(result) == 3
        assert result[0]["content"] == "First message"
        assert result[1]["content"] == "Second message"
        assert result[2]["content"] == "Third message"

    def test_only_returns_messages_for_specified_conversation(self, client):
        now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-1",
            title="Conv 1",
            created_at=now,
        )
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-2",
            title="Conv 2",
            created_at=now,
        )

        client.add_message(
            user_id="user-123",
            conversation_id="conv-1",
            message_id="msg-a",
            role="user",
            content="Message in conv 1",
            timestamp=now + timedelta(seconds=10),
        )
        client.add_message(
            user_id="user-123",
            conversation_id="conv-2",
            message_id="msg-b",
            role="user",
            content="Message in conv 2",
            timestamp=now + timedelta(seconds=20),
        )

        result = client.get_messages(user_id="user-123", conversation_id="conv-1")

        assert len(result) == 1
        assert result[0]["content"] == "Message in conv 1"


class TestConversationUpdatedAtAfterMessage:
    """Tests that adding a message updates the conversation's ordering."""

    def test_conversation_moves_to_top_after_new_message(self, client):
        base_time = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

        # Create two conversations, conv-old first
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-old",
            title="Old",
            created_at=base_time,
        )
        client.create_conversation(
            user_id="user-123",
            conversation_id="conv-new",
            title="New",
            created_at=base_time + timedelta(hours=1),
        )

        # At this point, conv-new should be first
        convs = client.get_conversations(user_id="user-123")
        assert convs[0]["conversation_id"] == "conv-new"

        # Now add a message to the old conversation
        client.add_message(
            user_id="user-123",
            conversation_id="conv-old",
            message_id="msg-update",
            role="user",
            content="Updating old conversation",
            timestamp=base_time + timedelta(hours=2),
        )

        # Now conv-old should be first (most recently updated)
        convs = client.get_conversations(user_id="user-123")
        assert convs[0]["conversation_id"] == "conv-old"
