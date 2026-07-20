"""Financial Research MCP Server.

Exposes tools for retrieving stock quotes, company profiles, and market summaries
via the Model Context Protocol using Streamable HTTP transport on port 8001.

Built with the MCP SDK's FastMCP server and the Strands Agents @tool decorator pattern.
"""

import json
import logging
import os

import boto3
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server import FastMCP

from mcp_servers.financial_research.data_provider import (
    DataSourceUnavailableError,
    get_company_profile_data,
    get_market_summary_data,
    get_stock_quote_data,
    is_valid_ticker,
)
from mcp_servers.shared.errors import MCPError

logger = logging.getLogger(__name__)

# Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AGENTCORE_RUNTIME_ARN = os.environ.get("AGENTCORE_RUNTIME_ARN", "")

# Create the MCP server instance configured for Streamable HTTP on port 8001
mcp = FastMCP(
    name="financial-research",
    host="0.0.0.0",
    port=8001,
    streamable_http_path="/mcp",
)


# Health endpoint for systemd watchdog monitoring
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for process manager monitoring."""
    return JSONResponse({"status": "healthy", "service": "financial-research-mcp"})


def register_with_agentcore() -> dict | None:
    """Register the Financial Research MCP server with Bedrock AgentCore for discoverability.

    Uses the AgentCore API to register this MCP server's endpoint and tool capabilities,
    making it discoverable by agents managed through AgentCore.

    Returns:
        Registration response dict on success, or None if registration is skipped/fails.
    """
    if not AGENTCORE_RUNTIME_ARN:
        logger.info(
            "AGENTCORE_RUNTIME_ARN not set — skipping AgentCore registration. "
            "Set this environment variable in production for discoverability."
        )
        return None

    try:
        client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
        response = client.update_agent_runtime(
            agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
            description="Financial Research MCP Server — provides stock quotes, company profiles, and market summaries",
            agentRuntimeEndpoint={
                "networkConfiguration": {
                    "networkMode": "PUBLIC",
                },
            },
        )
        logger.info(
            "Successfully registered Financial Research MCP with AgentCore: %s",
            AGENTCORE_RUNTIME_ARN,
        )
        return response
    except Exception as e:
        logger.warning(
            "Failed to register with AgentCore (non-fatal): %s", str(e)
        )
        return None


@mcp.tool()
def get_stock_quote(ticker: str) -> str:
    """Get the current stock quote for a ticker symbol.

    Returns price, change percentage, and trading volume for the specified stock.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "MSFT", "AMP").

    Returns:
        JSON string with ticker, price, change_pct, and volume fields.
    """
    ticker = ticker.upper().strip()

    if not ticker or not is_valid_ticker(ticker):
        error = MCPError(
            error_type="INVALID_TICKER",
            message=f"Ticker symbol '{ticker}' was not found. Please provide a valid ticker symbol.",
        )
        return error.to_json()

    try:
        data = get_stock_quote_data(ticker)
        return json.dumps(data)
    except DataSourceUnavailableError:
        error = MCPError(
            error_type="DATA_SOURCE_UNAVAILABLE",
            message="Unable to reach the financial data source. Please try again later.",
        )
        return error.to_json()


@mcp.tool()
def get_company_profile(ticker: str) -> str:
    """Get the company profile for a ticker symbol.

    Returns company name, sector, market capitalization, and a brief description.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "MSFT", "AMP").

    Returns:
        JSON string with ticker, name, sector, market_cap, and description fields.
        Description is truncated to 500 characters maximum.
    """
    ticker = ticker.upper().strip()

    if not ticker or not is_valid_ticker(ticker):
        error = MCPError(
            error_type="INVALID_TICKER",
            message=f"Ticker symbol '{ticker}' was not found. Please provide a valid ticker symbol.",
        )
        return error.to_json()

    try:
        data = get_company_profile_data(ticker)
        return json.dumps(data)
    except DataSourceUnavailableError:
        error = MCPError(
            error_type="DATA_SOURCE_UNAVAILABLE",
            message="Unable to reach the financial data source. Please try again later.",
        )
        return error.to_json()


@mcp.tool()
def get_market_summary() -> str:
    """Get a summary of the current market conditions.

    Returns major market indices with their values and daily changes,
    along with the top gaining and losing stocks.

    Returns:
        JSON string with indices (list of {name, value, change_pct}),
        top_gainers (list of ticker symbols), and top_losers (list of ticker symbols).
    """
    try:
        data = get_market_summary_data()
        return json.dumps(data)
    except DataSourceUnavailableError:
        error = MCPError(
            error_type="DATA_SOURCE_UNAVAILABLE",
            message="Unable to reach the financial data source. Please try again later.",
        )
        return error.to_json()


def main():
    """Run the Financial Research MCP server."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Financial Research MCP server on port 8001")

    # Register with AgentCore for discoverability (non-blocking, best-effort)
    register_with_agentcore()

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
