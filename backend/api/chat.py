"""Chat API endpoints for sending messages and managing conversations."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent.runtime import AgentResponse, ToolInvocationDetail, create_agent, process_message
from backend.db.dynamodb import DynamoDBClient
from backend.middleware.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# --- Request / Response Models ---


class ChatMessageRequest(BaseModel):
    """Request body for sending a chat message."""

    message: str = Field(..., min_length=1, max_length=2000, description="Message content (1-2000 characters)")
    conversation_id: str | None = Field(default=None, description="Existing conversation ID. If null, a new conversation is created.")


class CreateConversationRequest(BaseModel):
    """Request body for creating a new conversation."""

    title: str = Field(..., min_length=1, max_length=100, description="Conversation title")


class ConversationResponse(BaseModel):
    """Response model for a conversation."""

    conversation_id: str
    title: str
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    """Response model for a message in a conversation."""

    conversation_id: str
    message_id: str
    role: str
    content: str
    timestamp: str
    tool_invocations: list[dict] = Field(default_factory=list)
    trace: dict | None = None


class ConversationMessagesResponse(BaseModel):
    """Response model for getting messages in a conversation."""

    conversation_id: str
    messages: list[MessageResponse]


class ToolInvocationResponse(BaseModel):
    """Tool invocation details included in the chat response."""

    mcp_server: str
    tool_name: str
    status: str
    duration_ms: float


class ChatMessageResponse(BaseModel):
    """Response from the chat message endpoint."""

    conversation_id: str
    message_id: str
    role: str = "assistant"
    content: str
    tool_invocations: list[ToolInvocationResponse] = Field(default_factory=list)
    trace: dict | None = None
    timestamp: str


# --- Helpers ---


def _generate_id() -> str:
    """Generate a unique ID for conversations and messages."""
    return uuid.uuid4().hex


def _get_db_client() -> DynamoDBClient:
    """Get a DynamoDB client instance."""
    return DynamoDBClient()


def _build_tool_invocation_response(invocations: list[ToolInvocationDetail]) -> list[ToolInvocationResponse]:
    """Convert agent tool invocation details to response models."""
    return [
        ToolInvocationResponse(
            mcp_server=inv.mcp_server,
            tool_name=inv.tool_name,
            status=inv.status,
            duration_ms=inv.duration_ms,
        )
        for inv in invocations
    ]


def _build_tool_invocations_for_storage(invocations: list[ToolInvocationDetail]) -> list[dict]:
    """Convert agent tool invocation details to dicts for DynamoDB storage."""
    return [
        {
            "mcp_server": inv.mcp_server,
            "tool_name": inv.tool_name,
            "status": inv.status,
            "duration_ms": inv.duration_ms,
        }
        for inv in invocations
    ]


# --- Endpoints ---


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    responses={
        400: {"description": "Validation error"},
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def send_message(
    request: ChatMessageRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ChatMessageResponse:
    """Send a message to the AI agent and receive a response.

    Validates message length (1-2000 chars), invokes the agent, persists both
    the user message and assistant response to DynamoDB, and returns the response
    with tool invocation details.

    If no conversation_id is provided, a new conversation is created automatically.
    Handles agent errors by returning an error message indicating which MCP server/tool failed.
    Handles 30-second timeout with a timeout response.
    """
    db = _get_db_client()
    now = datetime.now(timezone.utc)

    # Determine or create conversation
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = _generate_id()
        # Auto-generate title from first 50 chars of the message
        title = request.message[:50].strip()
        if len(request.message) > 50:
            title += "..."
        db.create_conversation(
            user_id=user.user_id,
            conversation_id=conversation_id,
            title=title,
            created_at=now,
        )

    # Persist user message
    user_message_id = _generate_id()
    db.add_message(
        user_id=user.user_id,
        conversation_id=conversation_id,
        message_id=user_message_id,
        role="user",
        content=request.message,
        timestamp=now,
    )

    # Invoke the agent
    try:
        agent = create_agent()
        agent_response: AgentResponse = await process_message(agent, request.message)
    except Exception as e:
        logger.error("Failed to invoke agent: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to process message. Please try again.",
            },
        )

    # Handle timeout
    if agent_response.timed_out:
        response_content = agent_response.text
    else:
        response_content = agent_response.text

    # Build tool invocation data
    tool_invocations_response = _build_tool_invocation_response(agent_response.tool_invocations)
    tool_invocations_storage = _build_tool_invocations_for_storage(agent_response.tool_invocations)

    # Persist assistant response
    assistant_message_id = _generate_id()
    assistant_timestamp = datetime.now(timezone.utc)

    db.add_message(
        user_id=user.user_id,
        conversation_id=conversation_id,
        message_id=assistant_message_id,
        role="assistant",
        content=response_content,
        timestamp=assistant_timestamp,
        tool_invocations=tool_invocations_storage,
    )

    return ChatMessageResponse(
        conversation_id=conversation_id,
        message_id=assistant_message_id,
        role="assistant",
        content=response_content,
        tool_invocations=tool_invocations_response,
        trace=None,
        timestamp=assistant_timestamp.isoformat(),
    )


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    responses={
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def list_conversations(
    user: CurrentUser = Depends(get_current_user),
) -> list[ConversationResponse]:
    """List conversations for the authenticated user.

    Returns up to 50 conversations ordered by most recent activity.
    """
    db = _get_db_client()
    try:
        conversations = db.get_conversations(user_id=user.user_id, limit=50)
    except Exception as e:
        logger.error("Failed to list conversations: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to retrieve conversations. Please try again.",
            },
        )

    return [
        ConversationResponse(
            conversation_id=conv["conversation_id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
        )
        for conv in conversations
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationMessagesResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Conversation not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_conversation_messages(
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ConversationMessagesResponse:
    """Get messages for a specific conversation in chronological order.

    Returns all messages for the conversation owned by the authenticated user.
    """
    db = _get_db_client()
    try:
        messages = db.get_messages(user_id=user.user_id, conversation_id=conversation_id)
    except Exception as e:
        logger.error("Failed to get messages for conversation %s: %s", conversation_id, str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to retrieve messages. Please try again.",
            },
        )

    if not messages:
        # Could be an empty conversation or non-existent one.
        # We still return an empty message list (valid for newly created conversations).
        pass

    return ConversationMessagesResponse(
        conversation_id=conversation_id,
        messages=[
            MessageResponse(
                conversation_id=msg.get("conversation_id", conversation_id),
                message_id=msg["message_id"],
                role=msg["role"],
                content=msg["content"],
                timestamp=msg["timestamp"],
                tool_invocations=msg.get("tool_invocations", []),
                trace=msg.get("trace"),
            )
            for msg in messages
        ],
    )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=201,
    responses={
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def create_conversation(
    request: CreateConversationRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ConversationResponse:
    """Create a new conversation.

    Creates a fresh conversation context with no prior message history.
    """
    db = _get_db_client()
    conversation_id = _generate_id()
    now = datetime.now(timezone.utc)

    try:
        conversation_data = db.create_conversation(
            user_id=user.user_id,
            conversation_id=conversation_id,
            title=request.title,
            created_at=now,
        )
    except Exception as e:
        logger.error("Failed to create conversation: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to create conversation. Please try again.",
            },
        )

    return ConversationResponse(
        conversation_id=conversation_data["conversation_id"],
        title=conversation_data["title"],
        created_at=conversation_data["created_at"],
        updated_at=conversation_data["updated_at"],
    )


@router.get(
    "/trace/{request_id}",
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Trace not found"},
    },
)
async def get_trace(
    request_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get trace data for a specific request.

    Returns trace spans showing the sequence of agent reasoning steps
    and tool calls for the given request.
    """
    # Trace data is stored as part of message data in DynamoDB.
    # The request_id corresponds to the message_id of the assistant response.
    db = _get_db_client()

    try:
        # Query for the message with this ID (it's the assistant message with trace data)
        response = db._table.get_item(
            Key={
                "PK": f"USER#{user.user_id}",
                "SK": f"MSG#{request_id}",
            }
        )
    except Exception as e:
        logger.error("Failed to get trace for request %s: %s", request_id, str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to retrieve trace data. Please try again.",
            },
        )

    item = response.get("Item")
    if not item:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": "Trace data not found for the specified request.",
            },
        )

    data = DynamoDBClient._convert_decimals_to_float(item.get("data", {}))
    trace = data.get("trace")

    return {
        "request_id": request_id,
        "trace": trace,
        "tool_invocations": data.get("tool_invocations", []),
    }
