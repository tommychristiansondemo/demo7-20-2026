"""Simulated financial data provider for the Financial Research MCP server.

Provides realistic financial data for demo purposes. In production, this would
be replaced with calls to a real financial data API (e.g., Alpha Vantage, Yahoo Finance).
"""

import random

# Simulated stock data for well-known tickers
_STOCK_DATA: dict[str, dict] = {
    "AAPL": {
        "name": "Apple Inc.",
        "sector": "Technology",
        "market_cap": 3_450_000_000_000,
        "description": (
            "Apple Inc. designs, manufactures, and markets smartphones, personal computers, "
            "tablets, wearables, and accessories worldwide. The company offers iPhone, Mac, iPad, "
            "and Apple Watch product lines, along with services including the App Store, Apple Music, "
            "Apple TV+, iCloud, and Apple Pay."
        ),
        "price": 237.49,
        "change_pct": 1.23,
        "volume": 54_321_000,
    },
    "MSFT": {
        "name": "Microsoft Corporation",
        "sector": "Technology",
        "market_cap": 3_120_000_000_000,
        "description": (
            "Microsoft Corporation develops and supports software, services, devices, and solutions "
            "worldwide. The company operates through Productivity and Business Processes, Intelligent "
            "Cloud, and More Personal Computing segments. Its products include Office, Azure, Windows, "
            "LinkedIn, and Xbox."
        ),
        "price": 449.82,
        "change_pct": 0.87,
        "volume": 22_145_000,
    },
    "GOOGL": {
        "name": "Alphabet Inc.",
        "sector": "Technology",
        "market_cap": 2_180_000_000_000,
        "description": (
            "Alphabet Inc. operates as a holding company. The company, through its subsidiaries, "
            "provides web-based search, advertisements, maps, software applications, mobile operating "
            "systems, consumer content, enterprise solutions, commerce, and hardware products."
        ),
        "price": 178.35,
        "change_pct": -0.45,
        "volume": 28_900_000,
    },
    "AMZN": {
        "name": "Amazon.com, Inc.",
        "sector": "Consumer Cyclical",
        "market_cap": 2_050_000_000_000,
        "description": (
            "Amazon.com, Inc. engages in the retail sale of consumer products, advertising, and "
            "subscription services through online and physical stores. The company operates through "
            "North America, International, and Amazon Web Services (AWS) segments providing cloud "
            "computing, storage, and database services."
        ),
        "price": 205.74,
        "change_pct": 2.15,
        "volume": 45_678_000,
    },
    "NVDA": {
        "name": "NVIDIA Corporation",
        "sector": "Technology",
        "market_cap": 3_350_000_000_000,
        "description": (
            "NVIDIA Corporation provides graphics and compute solutions. The company operates through "
            "Graphics and Compute & Networking segments. It offers GeForce GPUs for gaming, data center "
            "platforms for AI and high-performance computing, and networking solutions for cloud and "
            "enterprise environments."
        ),
        "price": 135.67,
        "change_pct": 3.42,
        "volume": 312_000_000,
    },
    "JPM": {
        "name": "JPMorgan Chase & Co.",
        "sector": "Financial Services",
        "market_cap": 680_000_000_000,
        "description": (
            "JPMorgan Chase & Co. is a financial holding company providing investment banking, "
            "financial services, and asset management. The company operates through Consumer & "
            "Community Banking, Corporate & Investment Bank, Commercial Banking, and Asset & Wealth "
            "Management segments."
        ),
        "price": 245.30,
        "change_pct": -0.32,
        "volume": 8_900_000,
    },
    "AMP": {
        "name": "Ameriprise Financial, Inc.",
        "sector": "Financial Services",
        "market_cap": 48_500_000_000,
        "description": (
            "Ameriprise Financial, Inc. provides financial planning, advisory, insurance, and wealth "
            "management services. The company operates through Advice & Wealth Management, Asset "
            "Management, and Retirement & Protection Solutions segments, serving individual and "
            "institutional clients."
        ),
        "price": 478.92,
        "change_pct": 0.65,
        "volume": 1_200_000,
    },
    "TSLA": {
        "name": "Tesla, Inc.",
        "sector": "Consumer Cyclical",
        "market_cap": 800_000_000_000,
        "description": (
            "Tesla, Inc. designs, develops, manufactures, and sells electric vehicles, energy "
            "generation and storage systems. The company operates through Automotive, and Energy "
            "Generation and Storage segments. It produces the Model S, Model 3, Model X, Model Y, "
            "and Cybertruck vehicles."
        ),
        "price": 252.40,
        "change_pct": -1.87,
        "volume": 98_000_000,
    },
    "META": {
        "name": "Meta Platforms, Inc.",
        "sector": "Technology",
        "market_cap": 1_520_000_000_000,
        "description": (
            "Meta Platforms, Inc. develops products that enable people to connect and share through "
            "mobile devices, PCs, virtual reality headsets, and wearables. The company operates "
            "Facebook, Instagram, Messenger, WhatsApp, and is investing in metaverse technologies "
            "through Reality Labs."
        ),
        "price": 595.30,
        "change_pct": 1.56,
        "volume": 15_400_000,
    },
    "BRK.B": {
        "name": "Berkshire Hathaway Inc.",
        "sector": "Financial Services",
        "market_cap": 990_000_000_000,
        "description": (
            "Berkshire Hathaway Inc. is a holding company owning subsidiaries in insurance, freight "
            "rail transportation, energy, manufacturing, retailing, and services. The company also "
            "holds significant equity investments in public companies including Apple, Bank of America, "
            "and Coca-Cola."
        ),
        "price": 473.15,
        "change_pct": 0.12,
        "volume": 3_200_000,
    },
}

# Valid ticker set for validation
VALID_TICKERS: set[str] = set(_STOCK_DATA.keys())


class DataSourceUnavailableError(Exception):
    """Raised when the external data source cannot be reached."""

    pass


def get_stock_quote_data(ticker: str) -> dict:
    """Get stock quote data for a ticker symbol.

    Args:
        ticker: The stock ticker symbol (e.g., "AAPL").

    Returns:
        Dictionary with price, change_pct, and volume.

    Raises:
        KeyError: If the ticker is not found.
    """
    ticker = ticker.upper().strip()
    if ticker not in _STOCK_DATA:
        raise KeyError(f"Ticker '{ticker}' not found")

    data = _STOCK_DATA[ticker]
    return {
        "ticker": ticker,
        "price": data["price"],
        "change_pct": data["change_pct"],
        "volume": data["volume"],
    }


def get_company_profile_data(ticker: str) -> dict:
    """Get company profile data for a ticker symbol.

    Args:
        ticker: The stock ticker symbol (e.g., "AAPL").

    Returns:
        Dictionary with name, sector, market_cap, and description (truncated to 500 chars).

    Raises:
        KeyError: If the ticker is not found.
    """
    ticker = ticker.upper().strip()
    if ticker not in _STOCK_DATA:
        raise KeyError(f"Ticker '{ticker}' not found")

    data = _STOCK_DATA[ticker]
    description = data["description"][:500]
    return {
        "ticker": ticker,
        "name": data["name"],
        "sector": data["sector"],
        "market_cap": data["market_cap"],
        "description": description,
    }


def get_market_summary_data() -> dict:
    """Get market summary including indices, top gainers, and top losers.

    Returns:
        Dictionary with indices, top_gainers, and top_losers.
    """
    indices = [
        {"name": "S&P 500", "value": 5_998.74, "change_pct": 0.58},
        {"name": "Dow Jones", "value": 44_025.81, "change_pct": 0.32},
        {"name": "NASDAQ", "value": 19_756.23, "change_pct": 0.89},
        {"name": "Russell 2000", "value": 2_312.45, "change_pct": -0.15},
    ]

    # Determine top gainers and losers from our stock data
    sorted_by_change = sorted(
        _STOCK_DATA.items(), key=lambda x: x[1]["change_pct"], reverse=True
    )
    top_gainers = [ticker for ticker, _ in sorted_by_change[:3]]
    top_losers = [ticker for ticker, _ in sorted_by_change[-3:]]

    return {
        "indices": indices,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
    }


def is_valid_ticker(ticker: str) -> bool:
    """Check if a ticker symbol is valid.

    Args:
        ticker: The stock ticker symbol to validate.

    Returns:
        True if the ticker exists in our data, False otherwise.
    """
    return ticker.upper().strip() in VALID_TICKERS
