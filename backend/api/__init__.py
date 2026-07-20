"""FastAPI application entry point.

Creates the main FastAPI app, wires up the auth and chat routers,
and exposes a /health endpoint for process manager monitoring.
"""

from fastapi import FastAPI

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router

app = FastAPI(
    title="Bedrock AgentCore Demo API",
    description="Backend API for the Building Agentic AI with Amazon Bedrock AgentCore demo application.",
    version="1.0.0",
)

# Wire up routers
app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/health", tags=["infrastructure"])
async def health_check() -> dict:
    """Health check endpoint for systemd watchdog and load balancer monitoring.

    Returns a simple status indicating the API service is running and
    accepting requests.
    """
    return {"status": "healthy", "service": "backend-api"}
