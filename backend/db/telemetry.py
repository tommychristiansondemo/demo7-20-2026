"""DynamoDB telemetry data access layer.

Table: agentcore-demo-telemetry
- PK: Always "TELEMETRY"
- SK: "{iso_timestamp}#{record_id}"

Stores the last 10 inference telemetry records in a rolling window.
"""

from dataclasses import dataclass
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TELEMETRY_TABLE_NAME = "agentcore-demo-telemetry"
MAX_RECORDS = 10


@dataclass
class TelemetryRecord:
    """A single telemetry record stored in DynamoDB."""

    record_id: str
    student_email: str
    message_preview: str
    total_latency_ms: float
    tool_call_count: int
    timestamp: str
    thinking_content: str


class TelemetryDBClient:
    """Client for the telemetry DynamoDB table."""

    def __init__(self, table_name: str = TELEMETRY_TABLE_NAME, endpoint_url: str | None = None):
        """Initialize the telemetry DynamoDB client.

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

    @staticmethod
    def _convert_floats_to_decimal(obj):
        """Recursively convert float values to Decimal for DynamoDB storage."""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: TelemetryDBClient._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [TelemetryDBClient._convert_floats_to_decimal(item) for item in obj]
        return obj

    @staticmethod
    def _convert_decimals_to_float(obj):
        """Recursively convert Decimal values back to float/int for application use."""
        if isinstance(obj, Decimal):
            if obj == int(obj):
                return int(obj)
            return float(obj)
        elif isinstance(obj, dict):
            return {k: TelemetryDBClient._convert_decimals_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [TelemetryDBClient._convert_decimals_to_float(item) for item in obj]
        return obj

    def put_record(self, record: TelemetryRecord) -> None:
        """Insert a telemetry record, enforcing rolling window.

        1. Query all records (PK = "TELEMETRY")
        2. If count >= 10, delete the item with the lowest SK (oldest)
        3. Put the new record with SK = "{timestamp}#{record_id}"
        """
        # Query current records to check count
        response = self._table.query(
            KeyConditionExpression=Key("PK").eq("TELEMETRY"),
            ScanIndexForward=True,  # ascending by SK (oldest first)
        )
        items = response.get("Items", [])

        # If at capacity, delete the oldest record
        if len(items) >= MAX_RECORDS:
            oldest = items[0]
            self._table.delete_item(
                Key={"PK": oldest["PK"], "SK": oldest["SK"]}
            )

        # Build and put the new item
        sk = f"{record.timestamp}#{record.record_id}"
        item = {
            "PK": "TELEMETRY",
            "SK": sk,
            "record_id": record.record_id,
            "student_email": record.student_email,
            "message_preview": record.message_preview,
            "total_latency_ms": record.total_latency_ms,
            "tool_call_count": record.tool_call_count,
            "timestamp": record.timestamp,
            "thinking_content": record.thinking_content,
        }
        self._table.put_item(Item=self._convert_floats_to_decimal(item))

    def get_feed(self) -> list[TelemetryRecord]:
        """Return all records ordered by timestamp descending."""
        response = self._table.query(
            KeyConditionExpression=Key("PK").eq("TELEMETRY"),
            ScanIndexForward=False,  # descending by SK (newest first)
        )
        items = response.get("Items", [])

        records = []
        for item in items:
            item = self._convert_decimals_to_float(item)
            records.append(
                TelemetryRecord(
                    record_id=item["record_id"],
                    student_email=item["student_email"],
                    message_preview=item["message_preview"],
                    total_latency_ms=item["total_latency_ms"],
                    tool_call_count=item["tool_call_count"],
                    timestamp=item["timestamp"],
                    thinking_content=item.get("thinking_content", ""),
                )
            )
        return records

    def get_thinking(self, record_id: str) -> str | None:
        """Return extended thinking content for a specific record.

        Scans all telemetry records and finds the one matching the record_id.

        Args:
            record_id: The unique identifier of the telemetry record.

        Returns:
            The thinking content string, or None if the record is not found.
        """
        response = self._table.query(
            KeyConditionExpression=Key("PK").eq("TELEMETRY"),
        )
        items = response.get("Items", [])

        for item in items:
            if item.get("record_id") == record_id:
                return item.get("thinking_content", "")
        return None


def create_table(dynamodb_resource=None, table_name: str = TELEMETRY_TABLE_NAME):
    """Create the telemetry DynamoDB table.

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
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return table
