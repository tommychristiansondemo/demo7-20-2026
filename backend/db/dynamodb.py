"""DynamoDB data access layer using single-table design.

Table: agentcore-demo-conversations
- PK: USER#{user_id}
- SK: CONV#{conversation_id} or MSG#{message_id}
- GSI1PK: USER#{user_id}
- GSI1SK: UPDATED#{updated_at}
- type: "conversation" or "message"
- data: Full entity payload
- ttl: Epoch seconds for automatic expiration
"""

import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = "agentcore-demo-conversations"
GSI1_NAME = "GSI1"

# Default TTL: 7 days from now (course duration + buffer)
DEFAULT_TTL_DAYS = 7


class DynamoDBClient:
    """Client wrapper for DynamoDB operations on the conversations table."""

    def __init__(self, table_name: str = TABLE_NAME, endpoint_url: str | None = None):
        """Initialize the DynamoDB client.

        Args:
            table_name: Name of the DynamoDB table.
            endpoint_url: Optional endpoint URL for local development/testing.
        """
        self._table_name = table_name
        kwargs: dict = {}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        self._dynamodb = boto3.resource("dynamodb", **kwargs)
        self._table = self._dynamodb.Table(table_name)

    @property
    def table_name(self) -> str:
        """Return the table name."""
        return self._table_name

    @staticmethod
    def _convert_floats_to_decimal(obj):
        """Recursively convert float values to Decimal for DynamoDB storage."""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: DynamoDBClient._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [DynamoDBClient._convert_floats_to_decimal(item) for item in obj]
        return obj

    @staticmethod
    def _convert_decimals_to_float(obj):
        """Recursively convert Decimal values back to float/int for application use."""
        if isinstance(obj, Decimal):
            if obj == int(obj):
                return int(obj)
            return float(obj)
        elif isinstance(obj, dict):
            return {k: DynamoDBClient._convert_decimals_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [DynamoDBClient._convert_decimals_to_float(item) for item in obj]
        return obj

    @staticmethod
    def _make_pk(user_id: str) -> str:
        """Create partition key for a user."""
        return f"USER#{user_id}"

    @staticmethod
    def _make_conversation_sk(conversation_id: str) -> str:
        """Create sort key for a conversation."""
        return f"CONV#{conversation_id}"

    @staticmethod
    def _make_message_sk(message_id: str) -> str:
        """Create sort key for a message."""
        return f"MSG#{message_id}"

    @staticmethod
    def _make_gsi1_sk(updated_at: datetime) -> str:
        """Create GSI1 sort key from a datetime."""
        return f"UPDATED#{updated_at.isoformat()}"

    @staticmethod
    def _compute_ttl(days: int = DEFAULT_TTL_DAYS) -> int:
        """Compute TTL as epoch seconds from now."""
        return int(time.time()) + (days * 86400)

    def create_conversation(
        self,
        user_id: str,
        conversation_id: str,
        title: str,
        created_at: datetime | None = None,
    ) -> dict:
        """Create a new conversation.

        Args:
            user_id: Cognito sub of the conversation owner.
            conversation_id: ULID of the conversation.
            title: Auto-generated title from first message.
            created_at: Timestamp of creation. Defaults to now (UTC).

        Returns:
            The conversation data as stored.
        """
        now = created_at or datetime.now(timezone.utc)
        conversation_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "title": title,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        item = {
            "PK": self._make_pk(user_id),
            "SK": self._make_conversation_sk(conversation_id),
            "GSI1PK": self._make_pk(user_id),
            "GSI1SK": self._make_gsi1_sk(now),
            "type": "conversation",
            "data": conversation_data,
            "ttl": self._compute_ttl(),
        }

        self._table.put_item(Item=self._convert_floats_to_decimal(item))
        return conversation_data

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        message_id: str,
        role: str,
        content: str,
        timestamp: datetime | None = None,
        tool_invocations: list[dict] | None = None,
        trace: dict | None = None,
    ) -> dict:
        """Add a message to a conversation.

        Also updates the conversation's updated_at timestamp in GSI1.

        Args:
            user_id: Cognito sub of the conversation owner.
            conversation_id: ULID of the conversation.
            message_id: ULID of the message.
            role: "user" or "assistant".
            content: Message content (1-2000 chars).
            timestamp: Message timestamp. Defaults to now (UTC).
            tool_invocations: List of tool invocations made during this message.
            trace: Trace data for this message.

        Returns:
            The message data as stored.
        """
        now = timestamp or datetime.now(timezone.utc)
        message_data = {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "role": role,
            "content": content,
            "timestamp": now.isoformat(),
            "tool_invocations": tool_invocations or [],
            "trace": trace,
        }

        item = {
            "PK": self._make_pk(user_id),
            "SK": self._make_message_sk(message_id),
            "GSI1PK": self._make_pk(user_id),
            "GSI1SK": self._make_gsi1_sk(now),
            "type": "message",
            "data": message_data,
            "ttl": self._compute_ttl(),
            "conversation_id": conversation_id,
        }

        self._table.put_item(Item=self._convert_floats_to_decimal(item))

        # Update the conversation's updated_at in GSI1 for ordering
        self._table.update_item(
            Key={
                "PK": self._make_pk(user_id),
                "SK": self._make_conversation_sk(conversation_id),
            },
            UpdateExpression="SET GSI1SK = :gsi1sk, #data.updated_at = :updated_at",
            ExpressionAttributeNames={"#data": "data"},
            ExpressionAttributeValues={
                ":gsi1sk": self._make_gsi1_sk(now),
                ":updated_at": now.isoformat(),
            },
        )

        return message_data

    def get_conversations(self, user_id: str, limit: int = 50) -> list[dict]:
        """Get conversations for a user, ordered by most recent activity.

        Uses GSI1 to query conversations ordered by updated_at descending.

        Args:
            user_id: Cognito sub of the user.
            limit: Maximum number of conversations to return (default 50).

        Returns:
            List of conversation data dicts, ordered by most recent activity.
        """
        response = self._table.query(
            IndexName=GSI1_NAME,
            KeyConditionExpression=Key("GSI1PK").eq(self._make_pk(user_id)),
            ScanIndexForward=False,
            FilterExpression="#item_type = :conv_type",
            ExpressionAttributeNames={"#item_type": "type"},
            ExpressionAttributeValues={":conv_type": "conversation"},
            Limit=limit,
        )

        items = response.get("Items", [])
        # Extract the data payload from each item
        conversations = [self._convert_decimals_to_float(item["data"]) for item in items]
        return conversations[:limit]

    def get_messages(self, user_id: str, conversation_id: str) -> list[dict]:
        """Get messages for a conversation, ordered chronologically.

        Queries messages by PK (user) and filters by conversation_id,
        using the SK prefix to get only messages, ordered by message_id (ULID).

        Args:
            user_id: Cognito sub of the user.
            conversation_id: ULID of the conversation.

        Returns:
            List of message data dicts, ordered chronologically by message_id.
        """
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._make_pk(user_id))
                & Key("SK").begins_with("MSG#")
            ),
            FilterExpression="#conv_id = :conv_id",
            ExpressionAttributeNames={"#conv_id": "conversation_id"},
            ExpressionAttributeValues={":conv_id": conversation_id},
            ScanIndexForward=True,
        )

        items = response.get("Items", [])
        # Extract the data payload from each item and sort by timestamp
        messages = [self._convert_decimals_to_float(item["data"]) for item in items]
        messages.sort(key=lambda m: m["timestamp"])
        return messages


def create_table(dynamodb_resource=None, table_name: str = TABLE_NAME):
    """Create the DynamoDB table with GSI1 and TTL configuration.

    This is used for local development/testing setup.

    Args:
        dynamodb_resource: Optional boto3 DynamoDB resource (for testing).
        table_name: Name of the table to create.

    Returns:
        The created table resource.
    """
    if dynamodb_resource is None:
        dynamodb_resource = boto3.resource("dynamodb")

    table = dynamodb_resource.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": GSI1_NAME,
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            }
        ],
        ProvisionedThroughput={
            "ReadCapacityUnits": 5,
            "WriteCapacityUnits": 5,
        },
    )

    # Enable TTL on the 'ttl' attribute
    client = dynamodb_resource.meta.client
    client.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={
            "Enabled": True,
            "AttributeName": "ttl",
        },
    )

    return table
