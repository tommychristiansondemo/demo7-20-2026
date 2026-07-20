"""Knowledge Base MCP Server.

Exposes a query_knowledge_base tool for retrieval-augmented generation
over AWS Bedrock AgentCore documentation and course materials.
Uses FastMCP with Streamable HTTP transport on port 8002.
"""

import json
import logging
import os

import boto3
from mcp.server import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_servers.shared.errors import MCPError
from mcp_servers.shared.responses import KnowledgeBasePassage, KnowledgeBaseQueryResponse

logger = logging.getLogger(__name__)

# Configuration
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
PORT = 8002
RELEVANCE_THRESHOLD = 0.3
MAX_PASSAGES = 5
MAX_QUERY_LENGTH = 1000

# AgentCore registration configuration
AGENTCORE_ENABLED = os.environ.get("AGENTCORE_ENABLED", "false").lower() == "true"
SERVICE_NAME = "knowledge-base-mcp"
SERVICE_DESCRIPTION = "MCP server for querying AWS Bedrock AgentCore documentation and course materials via RAG"

# Create the MCP server instance
mcp = FastMCP(
    name="knowledge-base-mcp",
    host="0.0.0.0",
    port=PORT,
    streamable_http_path="/mcp",
)


# Health endpoint for systemd watchdog monitoring
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for process manager monitoring."""
    return JSONResponse({"status": "healthy", "service": "knowledge-base-mcp"})


def _get_bedrock_agent_runtime_client():
    """Create a boto3 client for Bedrock Agent Runtime."""
    return boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)


@mcp.tool()
def query_knowledge_base(query: str) -> str:
    """Query the knowledge base for relevant passages about AWS Bedrock AgentCore and course materials.

    Searches the knowledge base and returns up to 5 passages that are relevant
    to the query, each with a relevance score of at least 0.3.

    Args:
        query: The search query string (1-1000 characters).

    Returns:
        JSON string containing matching passages with text, source title,
        section ID, and relevance score.
    """
    # Validate query
    if not query or not query.strip():
        error = MCPError(
            error_type="INVALID_QUERY",
            message="Query must not be empty.",
        )
        return error.to_json()

    if len(query) > MAX_QUERY_LENGTH:
        error = MCPError(
            error_type="INVALID_QUERY",
            message=f"Query must not exceed {MAX_QUERY_LENGTH} characters. Received {len(query)} characters.",
        )
        return error.to_json()

    # Query the Bedrock Knowledge Base
    client = _get_bedrock_agent_runtime_client()

    try:
        response = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": MAX_PASSAGES,
                }
            },
        )
    except Exception as e:
        error = MCPError(
            error_type="DATA_SOURCE_UNAVAILABLE",
            message=f"Knowledge base query failed: {str(e)}",
        )
        return error.to_json()

    # Process results and filter by relevance score
    passages = []
    for result in response.get("retrievalResults", []):
        score = result.get("score", 0.0)
        if score < RELEVANCE_THRESHOLD:
            continue

        content = result.get("content", {})
        location = result.get("location", {})

        # Extract source title from location metadata
        s3_location = location.get("s3Location", {})
        source_uri = s3_location.get("uri", "")
        source_title = _extract_source_title(source_uri, result)

        # Extract section ID from metadata
        section_id = _extract_section_id(result)

        passage = KnowledgeBasePassage(
            text=content.get("text", ""),
            source_title=source_title,
            section_id=section_id,
            relevance_score=score,
        )
        passages.append(passage)

    # Cap at max passages
    passages = passages[:MAX_PASSAGES]

    # Build response
    if not passages:
        query_response = KnowledgeBaseQueryResponse(
            passages=[],
            message="No passages met the minimum relevance threshold of 0.3. Try rephrasing your query.",
        )
    else:
        query_response = KnowledgeBaseQueryResponse(
            passages=passages,
            message=None,
        )

    return query_response.model_dump_json()


def _extract_source_title(source_uri: str, result: dict) -> str:
    """Extract a source title from the retrieval result metadata."""
    # Try to get title from metadata if available
    metadata = result.get("metadata", {})
    if "source_title" in metadata:
        return metadata["source_title"]
    if "title" in metadata:
        return metadata["title"]

    # Fall back to extracting from S3 URI
    if source_uri:
        # Extract filename from S3 URI as title
        parts = source_uri.rstrip("/").split("/")
        if parts:
            filename = parts[-1]
            # Remove extension for cleaner title
            if "." in filename:
                return filename.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
            return filename

    return "Unknown Source"


def _extract_section_id(result: dict) -> str:
    """Extract a section identifier from the retrieval result metadata."""
    metadata = result.get("metadata", {})
    if "section_id" in metadata:
        return metadata["section_id"]
    if "x-amz-bedrock-kb-chunk-id" in metadata:
        return metadata["x-amz-bedrock-kb-chunk-id"]

    # Use location information as fallback
    location = result.get("location", {})
    loc_type = location.get("type", "")
    if loc_type == "S3":
        s3_location = location.get("s3Location", {})
        uri = s3_location.get("uri", "")
        if uri:
            return f"s3:{uri.split('/')[-1]}" if "/" in uri else f"s3:{uri}"

    return "unknown"


def _register_with_agentcore():
    """Register the MCP server with Bedrock AgentCore for discoverability.

    This registers the server's endpoint and capabilities so that agents
    can discover and connect to it via AgentCore's service registry.
    Registration is skipped if AGENTCORE_ENABLED is not set to 'true'.
    """
    if not AGENTCORE_ENABLED:
        logger.info("AgentCore registration disabled (set AGENTCORE_ENABLED=true to enable)")
        return

    try:
        client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
        client.register_mcp_server(
            name=SERVICE_NAME,
            description=SERVICE_DESCRIPTION,
            endpoint=f"http://localhost:{PORT}/mcp",
            transport="streamable-http",
            tools=["query_knowledge_base"],
        )
        logger.info(f"Successfully registered '{SERVICE_NAME}' with Bedrock AgentCore")
    except Exception as e:
        # Registration failure should not prevent the server from starting.
        # The server remains functional for direct connections.
        logger.warning(f"Failed to register with AgentCore: {e}. Server will continue without registration.")


def create_server() -> FastMCP:
    """Create and return the configured Knowledge Base MCP server."""
    return mcp


def main():
    """Start the Knowledge Base MCP server with Streamable HTTP transport."""
    logging.basicConfig(level=logging.INFO)
    _register_with_agentcore()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
