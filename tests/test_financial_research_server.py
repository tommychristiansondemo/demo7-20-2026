"""Unit tests for the Financial Research MCP server tools."""

import json
from unittest.mock import patch

import httpx
import pytest

from mcp_servers.financial_research.data_provider import (
    VALID_TICKERS,
    get_company_profile_data,
    get_market_summary_data,
    get_stock_quote_data,
    is_valid_ticker,
)
from mcp_servers.financial_research.server import (
    get_company_profile,
    get_market_summary,
    get_stock_quote,
    mcp,
    register_with_agentcore,
)


class TestGetStockQuote:
    """Tests for the get_stock_quote tool."""

    def test_valid_ticker_returns_quote(self):
        """Valid ticker returns price, change_pct, and volume."""
        result = json.loads(get_stock_quote("AAPL"))
        assert result["ticker"] == "AAPL"
        assert isinstance(result["price"], (int, float))
        assert isinstance(result["change_pct"], (int, float))
        assert isinstance(result["volume"], int)

    def test_valid_ticker_case_insensitive(self):
        """Ticker lookup is case-insensitive."""
        result = json.loads(get_stock_quote("aapl"))
        assert result["ticker"] == "AAPL"
        assert "price" in result

    def test_valid_ticker_with_whitespace(self):
        """Ticker lookup trims whitespace."""
        result = json.loads(get_stock_quote("  MSFT  "))
        assert result["ticker"] == "MSFT"
        assert "price" in result

    def test_invalid_ticker_returns_error(self):
        """Invalid ticker returns INVALID_TICKER error."""
        result = json.loads(get_stock_quote("INVALID"))
        assert result["error_type"] == "INVALID_TICKER"
        assert "message" in result
        assert "INVALID" in result["message"]

    def test_empty_ticker_returns_error(self):
        """Empty ticker returns INVALID_TICKER error."""
        result = json.loads(get_stock_quote(""))
        assert result["error_type"] == "INVALID_TICKER"

    def test_all_valid_tickers_return_quotes(self):
        """All known valid tickers return proper quotes."""
        for ticker in VALID_TICKERS:
            result = json.loads(get_stock_quote(ticker))
            assert "price" in result, f"Failed for ticker {ticker}"
            assert "change_pct" in result, f"Failed for ticker {ticker}"
            assert "volume" in result, f"Failed for ticker {ticker}"
            assert result["volume"] >= 0


class TestGetCompanyProfile:
    """Tests for the get_company_profile tool."""

    def test_valid_ticker_returns_profile(self):
        """Valid ticker returns name, sector, market_cap, and description."""
        result = json.loads(get_company_profile("AMP"))
        assert result["ticker"] == "AMP"
        assert result["name"] == "Ameriprise Financial, Inc."
        assert result["sector"] == "Financial Services"
        assert isinstance(result["market_cap"], (int, float))
        assert result["market_cap"] >= 0
        assert isinstance(result["description"], str)

    def test_description_max_500_chars(self):
        """Description is always at most 500 characters."""
        for ticker in VALID_TICKERS:
            result = json.loads(get_company_profile(ticker))
            assert len(result["description"]) <= 500, (
                f"Description for {ticker} exceeds 500 chars: {len(result['description'])}"
            )

    def test_invalid_ticker_returns_error(self):
        """Invalid ticker returns INVALID_TICKER error."""
        result = json.loads(get_company_profile("XYZ123"))
        assert result["error_type"] == "INVALID_TICKER"
        assert "message" in result

    def test_case_insensitive_lookup(self):
        """Ticker lookup is case-insensitive."""
        result = json.loads(get_company_profile("msft"))
        assert result["ticker"] == "MSFT"
        assert result["name"] == "Microsoft Corporation"


class TestGetMarketSummary:
    """Tests for the get_market_summary tool."""

    def test_returns_indices(self):
        """Market summary includes indices with name, value, change_pct."""
        result = json.loads(get_market_summary())
        assert "indices" in result
        assert len(result["indices"]) > 0
        for index in result["indices"]:
            assert "name" in index
            assert "value" in index
            assert "change_pct" in index
            assert isinstance(index["value"], (int, float))
            assert isinstance(index["change_pct"], (int, float))

    def test_returns_top_gainers(self):
        """Market summary includes top gainers as ticker symbols."""
        result = json.loads(get_market_summary())
        assert "top_gainers" in result
        assert isinstance(result["top_gainers"], list)
        assert len(result["top_gainers"]) > 0
        for ticker in result["top_gainers"]:
            assert isinstance(ticker, str)

    def test_returns_top_losers(self):
        """Market summary includes top losers as ticker symbols."""
        result = json.loads(get_market_summary())
        assert "top_losers" in result
        assert isinstance(result["top_losers"], list)
        assert len(result["top_losers"]) > 0
        for ticker in result["top_losers"]:
            assert isinstance(ticker, str)

    def test_includes_major_indices(self):
        """Market summary includes S&P 500, Dow Jones, and NASDAQ."""
        result = json.loads(get_market_summary())
        index_names = [idx["name"] for idx in result["indices"]]
        assert "S&P 500" in index_names
        assert "Dow Jones" in index_names
        assert "NASDAQ" in index_names


class TestDataProvider:
    """Tests for the data provider module."""

    def test_is_valid_ticker_true(self):
        """is_valid_ticker returns True for known tickers."""
        assert is_valid_ticker("AAPL") is True
        assert is_valid_ticker("aapl") is True
        assert is_valid_ticker("  AMP  ") is True

    def test_is_valid_ticker_false(self):
        """is_valid_ticker returns False for unknown tickers."""
        assert is_valid_ticker("INVALID") is False
        assert is_valid_ticker("") is False
        assert is_valid_ticker("ZZZ") is False

    def test_get_stock_quote_data_raises_for_invalid(self):
        """get_stock_quote_data raises KeyError for invalid ticker."""
        with pytest.raises(KeyError):
            get_stock_quote_data("INVALID")

    def test_get_company_profile_data_raises_for_invalid(self):
        """get_company_profile_data raises KeyError for invalid ticker."""
        with pytest.raises(KeyError):
            get_company_profile_data("INVALID")

    def test_get_market_summary_data_structure(self):
        """get_market_summary_data returns proper structure."""
        data = get_market_summary_data()
        assert "indices" in data
        assert "top_gainers" in data
        assert "top_losers" in data


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.fixture
    def app(self):
        """Get the Starlette ASGI app from FastMCP."""
        return mcp.streamable_http_app()

    @pytest.mark.asyncio
    async def test_health_returns_200(self, app):
        """Health endpoint returns 200 OK."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_correct_body(self, app):
        """Health endpoint returns the expected JSON body."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        body = response.json()
        assert body == {"status": "healthy", "service": "financial-research-mcp"}

    @pytest.mark.asyncio
    async def test_health_content_type_json(self, app):
        """Health endpoint returns application/json content type."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert "application/json" in response.headers["content-type"]


class TestAgentCoreRegistration:
    """Tests for AgentCore registration logic."""

    def test_registration_skipped_when_no_arn(self):
        """Registration returns None when AGENTCORE_RUNTIME_ARN is not set."""
        with patch.dict("os.environ", {"AGENTCORE_RUNTIME_ARN": ""}, clear=False):
            # Re-import to pick up the env var change
            from mcp_servers.financial_research import server
            with patch.object(server, "AGENTCORE_RUNTIME_ARN", ""):
                result = server.register_with_agentcore()
        assert result is None

    def test_registration_called_with_arn(self):
        """Registration calls AgentCore API when ARN is set."""
        mock_response = {"agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test"}
        with patch("mcp_servers.financial_research.server.AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test"):
            with patch("mcp_servers.financial_research.server.boto3.client") as mock_client:
                mock_client.return_value.update_agent_runtime.return_value = mock_response
                result = register_with_agentcore()
        assert result == mock_response
        mock_client.return_value.update_agent_runtime.assert_called_once()

    def test_registration_handles_api_error_gracefully(self):
        """Registration returns None and logs warning on API error."""
        with patch("mcp_servers.financial_research.server.AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test"):
            with patch("mcp_servers.financial_research.server.boto3.client") as mock_client:
                mock_client.return_value.update_agent_runtime.side_effect = Exception("API error")
                result = register_with_agentcore()
        assert result is None
