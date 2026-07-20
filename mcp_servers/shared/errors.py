"""Shared error types for MCP servers."""

import json
from dataclasses import asdict, dataclass


@dataclass
class MCPError:
    """Structured error returned by MCP server tools.

    Attributes:
        error_type: Category of the error (e.g., INVALID_TICKER, DATA_SOURCE_UNAVAILABLE, INVALID_QUERY).
        message: Human-readable description of what went wrong.
    """

    error_type: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Serialize the error to a dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize the error to a JSON string."""
        return json.dumps(self.to_dict())

    def to_mcp_response(self) -> dict:
        """Format as an MCP tool error response.

        Returns the error in the MCP content format with isError=True.
        """
        return {
            "content": [{"type": "text", "text": self.to_json()}],
            "isError": True,
        }
