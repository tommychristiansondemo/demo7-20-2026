"""Shared constants for the Bedrock AgentCore Demo application."""

# Port assignments for application services
API_PORT = 8000
FINANCIAL_MCP_PORT = 8001
KNOWLEDGE_BASE_MCP_PORT = 8002

# MCP server URLs (localhost for single-instance deployment)
FINANCIAL_MCP_URL = f"http://localhost:{FINANCIAL_MCP_PORT}/mcp"
KNOWLEDGE_BASE_MCP_URL = f"http://localhost:{KNOWLEDGE_BASE_MCP_PORT}/mcp"

# Service names for observability and logging
API_SERVICE_NAME = "backend-api"
FINANCIAL_MCP_SERVICE_NAME = "financial-research-mcp"
KNOWLEDGE_BASE_MCP_SERVICE_NAME = "knowledge-base-mcp"
AGENT_SERVICE_NAME = "agent-runtime"
