# Project Knowledge Base: Bedrock AgentCore Demo

## What This Application Is

This is a demo application for a one-day AWS class titled "Building Agentic AI with Amazon Bedrock AgentCore," taught to employees of Ameriprise Financial. It demonstrates real-world agentic AI patterns using Amazon Bedrock AgentCore, the Strands Agents SDK, and MCP (Model Context Protocol) servers.

Students access the application at https://www.awsteach.com.

## Architecture Overview

The application runs entirely on a single EC2 instance with supporting AWS managed services:

- **Frontend**: React 18 SPA (TypeScript, TailwindCSS) served via CloudFront CDN from S3
- **Backend API**: FastAPI (Python 3.12) on port 8000, handles auth and chat routing
- **Financial Research MCP Server**: Port 8001, provides stock quotes, company profiles, market summaries
- **Knowledge Base MCP Server**: Port 8002, queries AWS Bedrock Knowledge Bases for RAG
- **Agent Runtime**: Strands Agents SDK with Claude Sonnet, orchestrates tool calls across MCP servers
- **DynamoDB**: Stores conversation history using single-table design
- **Cognito**: User authentication with email verification, 60-min sessions, account lockout
- **CloudFront**: TLS termination, static asset caching (86400s), API proxying to EC2
- **Route 53**: DNS for www.awsteach.com and awsteach.com (apex) pointing to CloudFront

## Key Technologies

### Strands Agents SDK
- Open-source Python framework for building AI agents
- Used for both the agent runtime AND the MCP server implementations
- Agent uses `BedrockModel` with Claude Sonnet 4 for inference
- MCP servers use `@tool` decorator pattern via FastMCP
- Agent configured with `max_tool_calls=10` and 30-second timeout

### Model Context Protocol (MCP)
- Standard protocol for AI agents to interact with external tools
- MCP servers expose tools as structured function calls
- Transport: Streamable HTTP over localhost (ports 8001, 8002)
- Agent connects to MCP servers via `MCPClient` with `StreamableHTTPClientTransport`

### Amazon Bedrock AgentCore
- Managed services for deploying, securing, and observing AI agents in production
- Provides agent runtime management, observability (tracing), and service discovery
- MCP servers register with AgentCore for discoverability
- Agent emits trace spans for each tool invocation

## How the Chat Flow Works

1. Student sends message via React frontend to `POST /api/chat/message`
2. CloudFront proxies the request to the EC2 backend (port 8000)
3. Backend validates JWT token via Cognito's `get_user` API
4. Backend invokes the Strands Agent with the student's message
5. Agent sends prompt to Bedrock Claude with available tool definitions
6. Claude decides which tools to call (if any)
7. Agent calls tools on MCP servers via Streamable HTTP
8. MCP servers return structured results
9. Agent sends tool results back to Claude for synthesis
10. Claude generates final natural language response
11. Backend persists both messages to DynamoDB
12. Response (with tool invocation details and trace data) returned to frontend
13. Frontend displays response with tool invocation panel and trace viewer

## MCP Servers Detail

### Financial Research MCP (Port 8001)
- `get_stock_quote(ticker)` → price, change_pct, volume
- `get_company_profile(ticker)` → name, sector, market_cap, description (≤500 chars)
- `get_market_summary()` → indices, top_gainers, top_losers
- Uses simulated data for 10 tickers (AAPL, MSFT, GOOGL, AMZN, NVDA, JPM, AMP, TSLA, META, BRK.B)
- Returns `MCPError(error_type="INVALID_TICKER")` for unknown symbols
- Health endpoint: `GET /health`

### Knowledge Base MCP (Port 8002)
- `query_knowledge_base(query)` → up to 5 passages with relevance scores
- Queries Amazon Bedrock Knowledge Bases via boto3 `bedrock-agent-runtime` client
- Filters results: only returns passages with `relevance_score >= 0.3`
- Returns empty list with message when no passages meet threshold
- Validates query: 1-1000 characters, returns `MCPError(error_type="INVALID_QUERY")` for invalid
- Health endpoint: `GET /health`

## DynamoDB Design

Single-table design in table `agentcore-demo-conversations`:
- **PK**: `USER#{user_id}` (Cognito sub)
- **SK**: `CONV#{conversation_id}` or `MSG#{message_id}`
- **GSI1**: PK=`USER#{user_id}`, SK=`UPDATED#{updated_at}` — for listing conversations by recency
- **TTL**: Automatic expiration after 7 days
- Max 50 conversations returned per user, ordered by most recent activity

## Authentication Flow

1. Register: email + password + display name (2-50 chars) → Cognito creates user, sends verification email
2. Verify: enter 6-digit code from email → account confirmed
3. Sign in: email + password → Cognito returns access token (60-min lifetime)
4. All API calls include `Authorization: Bearer <access_token>` header
5. Backend validates token via `cognito.get_user(AccessToken=token)`
6. Account locks after 5 failed sign-in attempts (15-minute lockout)
7. Sign out: calls `cognito.global_sign_out` to invalidate tokens

## Observability

- Each tool invocation emits a trace span: MCP server name, tool name, duration_ms, success/failure
- Per-request metrics: total_latency_ms, tool_call_count, prompt_tokens, completion_tokens
- AgentCore observability integration (with fallback to file logging if emission fails)
- Trace data viewable in the frontend TraceViewer component within 3 seconds of completion

## Deployment Details

- EC2 instance: `ec2-44-211-240-31.compute-1.amazonaws.com` with admin IAM role (GodRole)
- Region: us-east-1
- Services managed by systemd with auto-restart (RestartSec=10, max 5 restarts per 60s)
- CloudFront distribution: E2UKNVKROFQ8T (d11j7cpsxc2m5c.cloudfront.net)
- Cognito User Pool: us-east-1_rP1lsuL3p
- S3 bucket for frontend: agentcore-demo-frontend-154833006816

## Project Structure

```
/home/ec2-user/demo/
├── frontend/          # React SPA (Vite + TypeScript + TailwindCSS)
│   └── src/
│       ├── auth/      # AuthContext, RouteGuard
│       ├── api/       # Centralized API client with interceptors
│       ├── components/# ChatInterface, ConversationSidebar, ToolInvocationPanel, TraceViewer
│       └── pages/     # RegisterPage, SignInPage, VerifyPage, DashboardPage, ChatPage
├── backend/
│   ├── api/           # FastAPI app, auth router, chat router
│   ├── db/            # DynamoDB data access layer
│   ├── middleware/    # JWT validation middleware
│   └── models/        # Pydantic models (conversation, auth)
├── mcp_servers/
│   ├── financial_research/  # Financial Research MCP server
│   ├── knowledge_base/      # Knowledge Base MCP server
│   └── shared/              # MCPError, response models
├── agent/
│   ├── runtime.py     # Strands Agent configuration and message processing
│   └── observability.py # TraceCollector, span emission, fallback logging
├── infra/             # CloudFormation templates (cloudfront, cognito, dynamodb, route53, systemd)
└── tests/             # pytest test suite (190 tests)
```

## Correctness Properties (Property-Based Testing)

The application uses Hypothesis for property-based testing with 16 formal properties:
1. Registration validates email, password policy, display name length
2. Expired tokens always redirect to sign-in
3-5. Financial MCP returns correct structures for valid tickers, errors for invalid
6-8. Knowledge Base returns ≤5 passages with scores ≥0.3, validates query length
9. Agent never exceeds 10 tool invocations per message
10. Every tool invocation displays MCP server name, tool name, status
11. Messages must be 1-2000 characters
12. Every trace span has MCP server, tool name, duration, status
13. Every completed request has latency, tool count, token counts
14-16. Messages persist in chronological order, conversations cap at 50, user isolation
