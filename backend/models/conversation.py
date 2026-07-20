"""Data models for conversations, messages, tool invocations, and trace data."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of a message sender."""

    USER = "user"
    ASSISTANT = "assistant"


class ToolInvocationStatus(str, Enum):
    """Status of a tool invocation."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SpanStatus(str, Enum):
    """Status of a trace span."""

    SUCCESS = "success"
    FAILURE = "failure"


class ToolInvocation(BaseModel):
    """A single tool invocation made by the agent during message processing."""

    mcp_server: str = Field(..., description="Name of the MCP server invoked")
    tool_name: str = Field(..., description="Name of the tool called")
    status: ToolInvocationStatus = Field(..., description="Current status of the invocation")
    duration_ms: float = Field(..., ge=0, description="Duration of the invocation in milliseconds")
    input: dict[str, Any] = Field(default_factory=dict, description="Input parameters passed to the tool")
    output: dict[str, Any] | None = Field(default=None, description="Output from the tool, null if pending or failed")


class TraceSpan(BaseModel):
    """A single span within a trace, representing one step of agent processing."""

    name: str = Field(..., description="Name of the span")
    mcp_server: str | None = Field(default=None, description="MCP server name, if this span is a tool call")
    tool_name: str | None = Field(default=None, description="Tool name, if this span is a tool call")
    duration_ms: float = Field(..., ge=0, description="Duration of the span in milliseconds")
    status: SpanStatus = Field(..., description="Whether this span succeeded or failed")


class TraceData(BaseModel):
    """Trace data for a completed agent request."""

    total_latency_ms: float = Field(..., ge=0, description="Total latency for the request in milliseconds")
    tool_call_count: int = Field(..., ge=0, description="Number of tool calls made")
    prompt_tokens: int = Field(..., ge=0, description="Number of prompt tokens used")
    completion_tokens: int = Field(..., ge=0, description="Number of completion tokens used")
    spans: list[TraceSpan] = Field(default_factory=list, description="Ordered list of trace spans")


class Message(BaseModel):
    """A single message in a conversation."""

    conversation_id: str = Field(..., description="ULID of the conversation this message belongs to")
    message_id: str = Field(..., description="ULID of this message")
    role: MessageRole = Field(..., description="Whether this message is from the user or assistant")
    content: str = Field(..., min_length=1, max_length=2000, description="Message content (1-2000 characters)")
    tool_invocations: list[ToolInvocation] = Field(default_factory=list, description="Tool invocations made during this message")
    trace: TraceData | None = Field(default=None, description="Trace data for this message, if available")
    timestamp: datetime = Field(..., description="ISO 8601 timestamp of when the message was created")


class Conversation(BaseModel):
    """A conversation between a user and the agent."""

    user_id: str = Field(..., description="Cognito sub of the conversation owner")
    conversation_id: str = Field(..., description="ULID of the conversation")
    title: str = Field(..., description="Auto-generated title from first message")
    created_at: datetime = Field(..., description="ISO 8601 timestamp of creation")
    updated_at: datetime = Field(..., description="ISO 8601 timestamp of last update")
