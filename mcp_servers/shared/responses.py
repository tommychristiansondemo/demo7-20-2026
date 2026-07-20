"""Response models for MCP server tools."""

from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    """Response from the get_stock_quote tool."""

    ticker: str = Field(..., description="Ticker symbol")
    price: float = Field(..., description="Current stock price")
    change_pct: float = Field(..., description="Price change percentage")
    volume: int = Field(..., ge=0, description="Trading volume")


class CompanyProfile(BaseModel):
    """Response from the get_company_profile tool."""

    ticker: str = Field(..., description="Ticker symbol")
    name: str = Field(..., description="Company name")
    sector: str = Field(..., description="Industry sector")
    market_cap: float = Field(..., ge=0, description="Market capitalization")
    description: str = Field(..., max_length=500, description="Company description (max 500 chars)")


class MarketIndex(BaseModel):
    """A single market index entry in a market summary."""

    name: str = Field(..., description="Index name (e.g., S&P 500)")
    value: float = Field(..., description="Current index value")
    change_pct: float = Field(..., description="Daily change percentage")


class MarketSummary(BaseModel):
    """Response from the get_market_summary tool."""

    indices: list[MarketIndex] = Field(..., description="Major market indices")
    top_gainers: list[str] = Field(..., description="Top gaining ticker symbols")
    top_losers: list[str] = Field(..., description="Top losing ticker symbols")


class KnowledgeBasePassage(BaseModel):
    """A single passage returned from a knowledge base query."""

    text: str = Field(..., description="Passage text content")
    source_title: str = Field(..., description="Title of the source document")
    section_id: str = Field(..., description="Section identifier within the source")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0.0-1.0)")


class KnowledgeBaseQueryResponse(BaseModel):
    """Response from the query_knowledge_base tool."""

    passages: list[KnowledgeBasePassage] = Field(
        default_factory=list,
        max_length=5,
        description="Matching passages (max 5)",
    )
    message: str | None = Field(
        default=None,
        description="Explanatory message, e.g. when no passages meet relevance threshold",
    )
