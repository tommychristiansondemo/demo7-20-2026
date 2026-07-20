"""Property-based tests for the DynamoDB data access layer.

Uses Hypothesis for property generation and moto for DynamoDB mocking.
"""

import uuid
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from moto import mock_aws

from backend.db.dynamodb import DynamoDBClient, TABLE_NAME, create_table


# --- Strategies ---

# Generate valid user IDs (non-empty alphanumeric with dashes/underscores)
user_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=20,
)

# Generate valid conversation IDs (ULID-like alphanumeric)
conversation_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=26,
)

# Generate valid message IDs (ULID-like alphanumeric)
message_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=26,
)

# Generate message content (1-200 chars for performance; property holds for any length up to 2000)
message_content_strategy = st.text(min_size=1, max_size=200)

# Generate conversation titles
title_strategy = st.text(min_size=1, max_size=50)

# Generate a role
role_strategy = st.sampled_from(["user", "assistant"])

# Generate a base timestamp
base_timestamp_strategy = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 1, 1),
    timezones=st.just(timezone.utc),
)


# --- Helper ---


def make_client(dynamodb_resource):
    """Create a DynamoDBClient connected to the given mocked DynamoDB resource."""
    db_client = DynamoDBClient.__new__(DynamoDBClient)
    db_client._table_name = TABLE_NAME
    db_client._dynamodb = dynamodb_resource
    db_client._table = dynamodb_resource.Table(TABLE_NAME)
    return db_client


# --- Property 14: Message persistence ordering ---

# Use a module-level mock so all hypothesis examples share one table
_mock_14 = mock_aws()
_dynamodb_14 = None
_client_14 = None


@pytest.fixture(autouse=True, scope="module")
def setup_module_mock():
    """Set up a single moto mock for all property tests in this module."""
    global _dynamodb_14, _client_14
    _mock_14.start()
    _dynamodb_14 = boto3.resource("dynamodb", region_name="us-east-1")
    create_table(dynamodb_resource=_dynamodb_14)
    _client_14 = make_client(_dynamodb_14)
    yield
    _mock_14.stop()


class TestMessagePersistenceOrdering:
    """Feature: bedrock-agentcore-demo, Property 14: Message persistence ordering"""

    @given(
        num_messages=st.integers(min_value=1, max_value=8),
        base_time=base_timestamp_strategy,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_messages_returned_in_chronological_order(
        self, num_messages, base_time, data
    ):
        """Feature: bedrock-agentcore-demo, Property 14: Message persistence ordering

        For any sequence of messages within a conversation, persisting and then
        retrieving them returns them in chronological order.

        Validates: Requirements 10.1
        """
        # Use unique user_id and conversation_id per example to avoid cross-contamination
        unique_id = uuid.uuid4().hex[:12]
        user_id = f"user14-{unique_id}"
        conversation_id = f"conv14-{unique_id}"

        _client_14.create_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            title="Test conversation",
            created_at=base_time,
        )

        # Generate messages with strictly increasing timestamps
        timestamps = [base_time + timedelta(seconds=i + 1) for i in range(num_messages)]

        # Generate unique message IDs
        message_ids = [f"msg-{unique_id}-{i}" for i in range(num_messages)]

        contents = [
            data.draw(message_content_strategy, label=f"content_{i}")
            for i in range(num_messages)
        ]
        roles = [
            data.draw(role_strategy, label=f"role_{i}")
            for i in range(num_messages)
        ]

        # Persist messages in shuffled order to test sorting
        insertion_order = data.draw(
            st.permutations(list(range(num_messages))), label="insertion_order"
        )
        for idx in insertion_order:
            _client_14.add_message(
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_ids[idx],
                role=roles[idx],
                content=contents[idx],
                timestamp=timestamps[idx],
            )

        # Retrieve messages
        retrieved = _client_14.get_messages(
            user_id=user_id, conversation_id=conversation_id
        )

        # Verify chronological order
        assert len(retrieved) == num_messages
        for i in range(len(retrieved) - 1):
            assert retrieved[i]["timestamp"] <= retrieved[i + 1]["timestamp"]

        # Verify content is preserved for each timestamp
        for i, ts in enumerate(timestamps):
            matching = [m for m in retrieved if m["timestamp"] == ts.isoformat()]
            assert len(matching) >= 1
            assert matching[0]["content"] == contents[i]


# --- Property 15: Conversation list ordering and limit ---


class TestConversationListOrderingAndLimit:
    """Feature: bedrock-agentcore-demo, Property 15: Conversation list ordering and limit"""

    @given(
        num_conversations=st.integers(min_value=1, max_value=10),
        base_time=base_timestamp_strategy,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_conversations_ordered_by_recent_activity_capped_at_50(
        self, num_conversations, base_time, data
    ):
        """Feature: bedrock-agentcore-demo, Property 15: Conversation list ordering and limit

        For any student with conversations, retrieving the conversation list returns
        them ordered by most recent activity, with the result capped at 50 conversations.

        Validates: Requirements 10.3
        """
        unique_id = uuid.uuid4().hex[:12]
        user_id = f"user15-{unique_id}"

        # Create conversations with strictly increasing timestamps
        for i in range(num_conversations):
            conv_id = f"conv15-{unique_id}-{i}"
            title = data.draw(title_strategy, label=f"title_{i}")
            _client_14.create_conversation(
                user_id=user_id,
                conversation_id=conv_id,
                title=title,
                created_at=base_time + timedelta(minutes=i),
            )

        # Retrieve conversations
        retrieved = _client_14.get_conversations(user_id=user_id)

        # Verify cap at 50
        assert len(retrieved) <= 50

        # Verify ordering: most recent activity first (descending updated_at)
        for i in range(len(retrieved) - 1):
            assert retrieved[i]["updated_at"] >= retrieved[i + 1]["updated_at"]

        # All conversations should be returned since num <= 50
        assert len(retrieved) == num_conversations

    def test_cap_at_50_conversations(self):
        """Verify the 50-conversation cap by creating 52 conversations.

        This is a dedicated example-based test because creating 52 items per
        hypothesis example would be prohibitively slow with moto.

        Validates: Requirements 10.3
        """
        unique_id = uuid.uuid4().hex[:12]
        user_id = f"user15cap-{unique_id}"
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        for i in range(52):
            _client_14.create_conversation(
                user_id=user_id,
                conversation_id=f"conv15cap-{unique_id}-{i:03d}",
                title=f"Conversation {i}",
                created_at=base_time + timedelta(minutes=i),
            )

        retrieved = _client_14.get_conversations(user_id=user_id)

        # Must be capped at 50
        assert len(retrieved) == 50

        # Must be ordered by most recent first
        for i in range(len(retrieved) - 1):
            assert retrieved[i]["updated_at"] >= retrieved[i + 1]["updated_at"]


# --- Property 16: Conversation isolation by user identity ---


class TestConversationIsolationByUserIdentity:
    """Feature: bedrock-agentcore-demo, Property 16: Conversation isolation by user identity"""

    @given(
        num_convs_a=st.integers(min_value=1, max_value=3),
        num_convs_b=st.integers(min_value=1, max_value=3),
        base_time=base_timestamp_strategy,
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_conversations_isolated_between_users(
        self, num_convs_a, num_convs_b, base_time
    ):
        """Feature: bedrock-agentcore-demo, Property 16: Conversation isolation by user identity

        For any two distinct authenticated users, retrieving conversations for one user
        never returns conversations belonging to the other user.

        Validates: Requirements 10.5
        """
        unique_id = uuid.uuid4().hex[:12]
        user_a = f"userA-{unique_id}"
        user_b = f"userB-{unique_id}"

        # Create conversations for user A
        conv_ids_a = []
        for i in range(num_convs_a):
            conv_id = f"convA-{unique_id}-{i}"
            conv_ids_a.append(conv_id)
            _client_14.create_conversation(
                user_id=user_a,
                conversation_id=conv_id,
                title=f"User A Conv {i}",
                created_at=base_time + timedelta(minutes=i),
            )

        # Create conversations for user B
        conv_ids_b = []
        for i in range(num_convs_b):
            conv_id = f"convB-{unique_id}-{i}"
            conv_ids_b.append(conv_id)
            _client_14.create_conversation(
                user_id=user_b,
                conversation_id=conv_id,
                title=f"User B Conv {i}",
                created_at=base_time + timedelta(minutes=i),
            )

        # Retrieve conversations for user A
        convs_a = _client_14.get_conversations(user_id=user_a)

        # Retrieve conversations for user B
        convs_b = _client_14.get_conversations(user_id=user_b)

        # User A should only see their own conversations
        conv_ids_in_a = {c["conversation_id"] for c in convs_a}
        assert conv_ids_in_a == set(conv_ids_a)
        assert not conv_ids_in_a.intersection(set(conv_ids_b))

        # User B should only see their own conversations
        conv_ids_in_b = {c["conversation_id"] for c in convs_b}
        assert conv_ids_in_b == set(conv_ids_b)
        assert not conv_ids_in_b.intersection(set(conv_ids_a))

        # Verify counts
        assert len(convs_a) == num_convs_a
        assert len(convs_b) == num_convs_b
