"""Property-based tests for Financial Research MCP Server.

Feature: bedrock-agentcore-demo, Property 3: Stock quote response structure
Feature: bedrock-agentcore-demo, Property 4: Company profile response structure and description length
Feature: bedrock-agentcore-demo, Property 5: Invalid ticker error response

Validates: Requirements 3.3, 3.4, 3.5
"""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from mcp_servers.financial_research.data_provider import VALID_TICKERS
from mcp_servers.financial_research.server import get_company_profile, get_stock_quote


# Strategy: pick any valid ticker from the known set
valid_ticker_strategy = st.sampled_from(sorted(VALID_TICKERS))

# Strategy: generate strings that are NOT valid tickers
invalid_ticker_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=20,
).filter(lambda t: t.upper().strip() not in VALID_TICKERS and len(t.strip()) > 0)


class TestStockQuoteResponseStructure:
    """Feature: bedrock-agentcore-demo, Property 3: Stock quote response structure"""

    @given(ticker=valid_ticker_strategy)
    @settings(max_examples=100, deadline=None)
    def test_valid_ticker_returns_price_change_volume(self, ticker):
        """Feature: bedrock-agentcore-demo, Property 3: Stock quote response structure

        For any valid ticker symbol, invoking the get_stock_quote tool SHALL return
        a response containing price (number), change_pct (number), and volume (number).

        Validates: Requirements 3.3
        """
        result = get_stock_quote(ticker)
        data = json.loads(result)

        # Response must not be an error
        assert "error_type" not in data, (
            f"Expected successful response for valid ticker '{ticker}', "
            f"got error: {data}"
        )

        # Must contain ticker field matching the input
        assert "ticker" in data
        assert data["ticker"] == ticker.upper().strip()

        # Must contain price as a number
        assert "price" in data
        assert isinstance(data["price"], (int, float))

        # Must contain change_pct as a number
        assert "change_pct" in data
        assert isinstance(data["change_pct"], (int, float))

        # Must contain volume as a number
        assert "volume" in data
        assert isinstance(data["volume"], (int, float))


class TestCompanyProfileResponseStructure:
    """Feature: bedrock-agentcore-demo, Property 4: Company profile response structure and description length"""

    @given(ticker=valid_ticker_strategy)
    @settings(max_examples=100, deadline=None)
    def test_valid_ticker_returns_profile_with_bounded_description(self, ticker):
        """Feature: bedrock-agentcore-demo, Property 4: Company profile response structure and description length

        For any valid ticker symbol, invoking the get_company_profile tool SHALL return
        a response containing name, sector, market_cap, and description fields,
        where description is no more than 500 characters.

        Validates: Requirements 3.4
        """
        result = get_company_profile(ticker)
        data = json.loads(result)

        # Response must not be an error
        assert "error_type" not in data, (
            f"Expected successful response for valid ticker '{ticker}', "
            f"got error: {data}"
        )

        # Must contain ticker field matching the input
        assert "ticker" in data
        assert data["ticker"] == ticker.upper().strip()

        # Must contain name as a string
        assert "name" in data
        assert isinstance(data["name"], str)
        assert len(data["name"]) > 0

        # Must contain sector as a string
        assert "sector" in data
        assert isinstance(data["sector"], str)
        assert len(data["sector"]) > 0

        # Must contain market_cap as a number
        assert "market_cap" in data
        assert isinstance(data["market_cap"], (int, float))

        # Must contain description as a string with max 500 chars
        assert "description" in data
        assert isinstance(data["description"], str)
        assert len(data["description"]) <= 500, (
            f"Description for '{ticker}' is {len(data['description'])} chars, "
            f"exceeds 500 char limit"
        )


class TestInvalidTickerErrorResponse:
    """Feature: bedrock-agentcore-demo, Property 5: Invalid ticker error response"""

    @given(ticker=invalid_ticker_strategy)
    @settings(max_examples=100, deadline=None)
    def test_invalid_ticker_returns_structured_error(self, ticker):
        """Feature: bedrock-agentcore-demo, Property 5: Invalid ticker error response

        For any string that does not correspond to a valid ticker symbol, invoking
        a Financial_Research_MCP tool SHALL return a structured error containing an
        error_type field and a descriptive message indicating the symbol was not found.

        Validates: Requirements 3.5
        """
        result = get_stock_quote(ticker)
        data = json.loads(result)

        # Must be a structured error response
        assert "error_type" in data, (
            f"Expected error response for invalid ticker '{ticker}', "
            f"got: {data}"
        )
        assert data["error_type"] == "INVALID_TICKER"

        # Must contain a descriptive message
        assert "message" in data
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0

    @given(ticker=invalid_ticker_strategy)
    @settings(max_examples=100, deadline=None)
    def test_invalid_ticker_company_profile_returns_structured_error(self, ticker):
        """Feature: bedrock-agentcore-demo, Property 5: Invalid ticker error response

        For any string that does not correspond to a valid ticker symbol, invoking
        the get_company_profile tool SHALL return a structured error containing an
        error_type field and a descriptive message indicating the symbol was not found.

        Validates: Requirements 3.5
        """
        result = get_company_profile(ticker)
        data = json.loads(result)

        # Must be a structured error response
        assert "error_type" in data, (
            f"Expected error response for invalid ticker '{ticker}', "
            f"got: {data}"
        )
        assert data["error_type"] == "INVALID_TICKER"

        # Must contain a descriptive message
        assert "message" in data
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0
