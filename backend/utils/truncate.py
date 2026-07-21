"""Message preview truncation utility."""


def truncate_message(message: str, max_length: int = 100) -> str:
    """Truncate a message to max_length characters.

    If the message exceeds max_length, truncate and append '...'
    The total output length is max_length + 3 (for the ellipsis)
    when truncation occurs, or the original length when it doesn't.

    Args:
        message: The original message text.
        max_length: Maximum characters before truncation (default 100).

    Returns:
        The message preview, with '...' appended if truncated.
    """
    if len(message) <= max_length:
        return message
    return message[:max_length] + "..."
