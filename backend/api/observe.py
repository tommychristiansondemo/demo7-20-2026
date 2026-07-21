"""Observability dashboard API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.db.telemetry import TelemetryDBClient
from backend.middleware.auth import CurrentUser, get_current_user
from backend.utils.metrics import compute_average_latency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/observe", tags=["observe"])


# --- Response Models ---


class TelemetryFeedItem(BaseModel):
    """A single telemetry feed item returned to the frontend."""

    record_id: str
    student_email: str
    message_preview: str
    total_latency_ms: float
    tool_call_count: int
    timestamp: str


class TelemetryFeedResponse(BaseModel):
    """Response containing the telemetry feed and average latency."""

    records: list[TelemetryFeedItem]
    average_latency_ms: float


class ThinkingResponse(BaseModel):
    """Response containing the thinking content for a specific record."""

    record_id: str
    thinking_content: str
    has_thinking: bool


# --- Helpers ---


def _get_telemetry_db() -> TelemetryDBClient:
    """Get a TelemetryDBClient instance."""
    return TelemetryDBClient()


# --- Endpoints ---


@router.get(
    "/feed",
    response_model=TelemetryFeedResponse,
    responses={
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
async def get_feed(
    user: CurrentUser = Depends(get_current_user),
) -> TelemetryFeedResponse:
    """Get the telemetry feed with the last 10 inference records.

    Returns all telemetry records ordered by timestamp descending,
    along with the average latency across all records.
    """
    try:
        db = _get_telemetry_db()
        records = db.get_feed()
    except Exception as e:
        logger.error("Failed to retrieve telemetry feed: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to retrieve telemetry feed.",
            },
        )

    average_latency = compute_average_latency(records)

    feed_items = [
        TelemetryFeedItem(
            record_id=r.record_id,
            student_email=r.student_email,
            message_preview=r.message_preview,
            total_latency_ms=r.total_latency_ms,
            tool_call_count=r.tool_call_count,
            timestamp=r.timestamp,
        )
        for r in records
    ]

    return TelemetryFeedResponse(
        records=feed_items,
        average_latency_ms=average_latency,
    )


@router.get(
    "/thinking/{record_id}",
    response_model=ThinkingResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Record not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_thinking(
    record_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ThinkingResponse:
    """Get the extended thinking content for a specific telemetry record.

    Returns the chain-of-thought reasoning that the model produced during
    inference for the specified record.
    """
    try:
        db = _get_telemetry_db()
        thinking_content = db.get_thinking(record_id)
    except Exception as e:
        logger.error("Failed to retrieve thinking for record %s: %s", record_id, str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to retrieve thinking content.",
            },
        )

    if thinking_content is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Telemetry record '{record_id}' not found.",
            },
        )

    return ThinkingResponse(
        record_id=record_id,
        thinking_content=thinking_content,
        has_thinking=bool(thinking_content),
    )
