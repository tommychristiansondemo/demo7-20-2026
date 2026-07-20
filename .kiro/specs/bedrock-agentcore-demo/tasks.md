# Implementation Plan: Bedrock AgentCore Demo

## Overview

This implementation plan breaks down the Bedrock AgentCore demo application into incremental coding tasks. The application consists of a React SPA frontend, a FastAPI backend, two MCP servers (Financial Research and Knowledge Base) built with the Strands Agents SDK, and a conversational agent runtime — all deployed on a single EC2 instance with supporting AWS infrastructure (CloudFront, Route 53, Cognito, DynamoDB).

Tasks are ordered so that foundational components (project structure, data models, infrastructure) come first, followed by backend services, MCP servers, agent runtime, frontend, and finally integration wiring.

## Tasks

- [x] 1. Set up project structure and shared infrastructure
  - [x] 1.1 Create project directory structure and configuration files
    - Create top-level directories: `frontend/`, `backend/`, `mcp_servers/financial_research/`, `mcp_servers/knowledge_base/`, `agent/`, `infra/`, `tests/`
    - Initialize Python project with `pyproject.toml` (Python 3.12, dependencies: fastapi, uvicorn, boto3, pydantic, strands-agents, hypothesis, pytest, moto)
    - Initialize React frontend with Vite + TypeScript + TailwindCSS (`package.json`, `tsconfig.json`, `vite.config.ts`)
    - Create shared constants file with port assignments (API: 8000, Financial MCP: 8001, Knowledge Base MCP: 8002)
    - _Requirements: 8.1_

  - [x] 1.2 Define shared data models and response schemas (Python)
    - Create `backend/models/conversation.py` with Pydantic models for Conversation, Message, ToolInvocation, and TraceData matching the design's data model schemas
    - Create `backend/models/auth.py` with Pydantic models for registration, sign-in, and verification request/response schemas
    - Create `mcp_servers/shared/errors.py` with the `MCPError` dataclass (`error_type`, `message`) and serialization helper
    - Create `mcp_servers/shared/responses.py` with response models for StockQuote, CompanyProfile, MarketSummary, KnowledgeBasePassage, and KnowledgeBaseQueryResponse
    - _Requirements: 3.3, 3.4, 3.5, 4.3, 4.4, 5.4, 9.1, 10.1_

  - [x] 1.3 Create DynamoDB table schema and data access layer
    - Create `backend/db/dynamodb.py` with a DynamoDB client wrapper using single-table design (PK: `USER#{user_id}`, SK: `CONV#{conversation_id}` or `MSG#{message_id}`)
    - Implement GSI1 (PK: `USER#{user_id}`, SK: `UPDATED#{updated_at}`) for listing conversations by recent activity
    - Implement methods: `create_conversation`, `add_message`, `get_conversations` (max 50, ordered by updated_at desc), `get_messages` (ordered chronologically)
    - Set TTL attribute for automatic expiration
    - _Requirements: 10.1, 10.3, 10.5_

  - [x] 1.4 Write property tests for DynamoDB data access layer
    - **Property 14: Message persistence ordering** — For any sequence of messages within a conversation, persisting and then retrieving them returns them in chronological order
    - **Property 15: Conversation list ordering and limit** — For any student with conversations, retrieving returns them ordered by most recent activity, capped at 50
    - **Property 16: Conversation isolation by user identity** — For any two distinct users, retrieving conversations for one never returns the other's conversations
    - Use moto to mock DynamoDB, Hypothesis for property generation
    - **Validates: Requirements 10.1, 10.3, 10.5**

- [x] 2. Implement Backend API — Authentication
  - [x] 2.1 Implement registration endpoint
    - Create `backend/api/auth.py` with FastAPI router
    - Implement `POST /api/auth/register` — validate email format, password policy, display name (2-50 chars), create user in Cognito, trigger verification email
    - Implement `POST /api/auth/verify` — confirm verification code, redirect to sign-in
    - Return appropriate error responses for duplicate email (400), invalid password (400), invalid display name (400), invalid email format (400), invalid/expired verification code (400)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 2.2 Write property test for registration input validation
    - **Property 1: Registration input validation** — For any input with invalid email, non-compliant password, or display name outside 2-50 chars, system rejects with specific error
    - Use Hypothesis strategies for generating invalid inputs (empty strings, strings >50 chars, malformed emails)
    - **Validates: Requirements 1.5, 1.6, 1.8**

  - [x] 2.3 Implement sign-in and session management endpoints
    - Implement `POST /api/auth/signin` — authenticate via Cognito, return JWT with 60-minute lifetime
    - Implement `POST /api/auth/signout` — invalidate session token
    - Implement generic error message for failed sign-in (not revealing which field was wrong)
    - Implement account lockout after 5 failed attempts (15-minute lock)
    - Handle Cognito unavailability with 503 response
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7_

  - [x] 2.4 Implement JWT validation middleware
    - Create `backend/middleware/auth.py` with FastAPI dependency that validates JWT tokens from Cognito
    - Reject expired tokens with redirect to sign-in
    - Extract `user_id` (Cognito sub) from valid tokens for downstream use
    - _Requirements: 2.6_

  - [x] 2.5 Write property test for expired token rejection
    - **Property 2: Expired token rejection** — For any HTTP request with an expired session token, system redirects to sign-in page
    - Generate tokens with various expiration times using Hypothesis
    - **Validates: Requirements 2.6**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Financial Research MCP Server
  - [x] 4.1 Implement Financial Research MCP server with stock quote and company profile tools
    - Create `mcp_servers/financial_research/server.py` using Strands Agents SDK with `@tool` decorator
    - Implement `get_stock_quote` tool — accepts ticker string, returns `{price, change_pct, volume}` from external data source
    - Implement `get_company_profile` tool — accepts ticker string, returns `{name, sector, market_cap, description}` with description truncated to 500 chars
    - Implement `get_market_summary` tool — returns `{indices: [{name, value, change_pct}], top_gainers: [ticker], top_losers: [ticker]}`
    - Configure Streamable HTTP transport on port 8001
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 4.2 Implement error handling and AgentCore registration for Financial Research MCP
    - Return `MCPError(error_type="INVALID_TICKER", message="...")` for invalid ticker symbols
    - Return `MCPError(error_type="DATA_SOURCE_UNAVAILABLE", message="...")` when external API is unreachable
    - Implement AgentCore registration for discoverability
    - Add `/health` endpoint for process manager monitoring
    - _Requirements: 3.5, 3.6, 3.7_

  - [x] 4.3 Write property tests for Financial Research MCP
    - **Property 3: Stock quote response structure** — For any valid ticker, response contains price (number), change_pct (number), volume (number)
    - **Property 4: Company profile response structure and description length** — For any valid ticker, response contains name, sector, market_cap, description (≤500 chars)
    - **Property 5: Invalid ticker error response** — For any invalid ticker string, response is a structured error with error_type and message
    - Use mocked external data source, Hypothesis for ticker generation
    - **Validates: Requirements 3.3, 3.4, 3.5**

- [x] 5. Implement Knowledge Base MCP Server
  - [x] 5.1 Implement Knowledge Base MCP server with query tool
    - Create `mcp_servers/knowledge_base/server.py` using Strands Agents SDK with `@tool` decorator
    - Implement `query_knowledge_base` tool — accepts query string (1-1000 chars), queries Amazon Bedrock Knowledge Bases
    - Return up to 5 passages with `{text, source_title, section_id, relevance_score}`
    - Filter results to only return passages with relevance_score ≥ 0.3
    - Return empty passage list with explanatory message when no passages meet threshold
    - Configure Streamable HTTP transport on port 8002
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 5.2 Implement error handling and AgentCore registration for Knowledge Base MCP
    - Return `MCPError(error_type="INVALID_QUERY", message="...")` for empty or >1000 char queries
    - Implement AgentCore registration for discoverability
    - Add `/health` endpoint for process manager monitoring
    - _Requirements: 4.6, 4.7_

  - [x] 5.3 Write property tests for Knowledge Base MCP
    - **Property 6: Knowledge base query response structure** — For any valid query (1-1000 chars), returns at most 5 passages each with text, source_title, section_id, relevance_score
    - **Property 7: Relevance score filtering** — For any query, all returned passages have relevance_score ≥ 0.3; if none meet threshold, returns empty list with message
    - **Property 8: Knowledge base query validation** — For any empty or >1000 char query, returns structured error without performing lookup
    - Use mocked Bedrock Knowledge Base, Hypothesis for query string generation
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.7**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Strands Agent Runtime
  - [x] 7.1 Implement agent runtime with MCP client connections
    - Create `agent/runtime.py` using Strands Agent with BedrockModel (Claude Sonnet)
    - Configure MCPClient connections to Financial Research (localhost:8001) and Knowledge Base (localhost:8002) via Streamable HTTP transport
    - Set `max_tool_calls=10` per message processing cycle
    - Implement 30-second timeout for request processing
    - Define system prompt for class context
    - _Requirements: 5.1, 5.2, 5.3, 5.7_

  - [x] 7.2 Implement agent observability and trace span emission
    - Implement trace span emission for each tool invocation (MCP server name, tool name, duration_ms, success/failure status)
    - Log each user message, LLM inference call, and tool invocation via AgentCore observability
    - Collect per-request metrics: total_latency_ms, tool_call_count, prompt_tokens, completion_tokens
    - Implement fallback logging when trace emission fails (continue processing, log to fallback file)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 7.3 Write property tests for agent runtime
    - **Property 9: Agent tool invocation limit** — For any student message, total tool invocations ≤ 10
    - **Property 12: Trace span completeness** — For any tool invocation, trace span contains MCP server name, tool name, duration_ms, success/failure
    - **Property 13: Request observability metrics** — For any completed request, observability data includes total_latency_ms, tool_call_count, prompt_tokens, completion_tokens
    - Use mocked Bedrock and MCP servers, Hypothesis for message generation
    - **Validates: Requirements 5.3, 9.1, 9.4**

- [x] 8. Implement Backend API — Chat and Conversations
  - [x] 8.1 Implement chat message endpoint
    - Create `backend/api/chat.py` with FastAPI router
    - Implement `POST /api/chat/message` — validate message length (1-2000 chars), invoke agent, persist message and response to DynamoDB, return response with tool invocation details
    - Include tool invocation display data (MCP server name, tool name, status) in response
    - Handle agent errors by returning error message indicating which MCP server/tool failed
    - Handle 30-second timeout with timeout response
    - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 10.1_

  - [x] 8.2 Write property tests for chat message validation
    - **Property 11: Chat message length validation** — For any empty or >2000 char message, system rejects with validation message
    - **Property 10: Tool invocation display completeness** — For any tool invocation, response includes MCP server name, tool name, and status
    - Use Hypothesis for message string generation
    - **Validates: Requirements 5.4, 5.8**

  - [x] 8.3 Implement conversation management endpoints
    - Implement `GET /api/chat/conversations` — list up to 50 conversations ordered by most recent activity for authenticated user
    - Implement `GET /api/chat/conversations/{id}` — get messages for a conversation in chronological order
    - Implement `POST /api/chat/conversations` — create new conversation
    - Implement `GET /api/chat/trace/{request_id}` — get trace data for a specific request
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Frontend — Authentication
  - [x] 10.1 Create React app shell and routing
    - Set up React Router with routes: `/register`, `/signin`, `/verify`, `/dashboard`, `/chat`
    - Create `AuthModule` component with Cognito integration via AWS Amplify
    - Implement auth state management (signed in/out, session token storage, expiration handling)
    - Implement route guards redirecting unauthenticated users to sign-in
    - _Requirements: 2.2, 2.6_

  - [x] 10.2 Implement registration and verification forms
    - Create registration form with email, password, and display name fields
    - Implement client-side validation: email format, password policy display, display name 2-50 chars
    - Display inline field-level error messages for validation failures
    - Implement verification code form with resend option
    - Handle error responses: duplicate email, invalid password, invalid display name, invalid email format, invalid/expired verification code
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 10.3 Implement sign-in and sign-out
    - Create sign-in form with email and password fields
    - Display generic error message on failed sign-in (not revealing which field is wrong)
    - Display account locked message when locked (15-min lockout)
    - Display service unavailable message when Cognito is down
    - Implement sign-out button that invalidates session and redirects to sign-in page
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.7_

- [x] 11. Implement Frontend — Chat Interface
  - [x] 11.1 Implement chat interface and message display
    - Create `ChatInterface` component with message input (1-2000 char validation), message list, and streaming response display
    - Implement loading indicator while agent processes (up to 30 seconds)
    - Display timeout message if agent does not respond within 30 seconds
    - Display client-side validation error for empty or >2000 char messages
    - Implement error display when message fails to persist (retain unsent message text in input)
    - _Requirements: 5.1, 5.5, 5.7, 5.8, 10.2_

  - [x] 11.2 Implement tool invocation panel and trace viewer
    - Create `ToolInvocationPanel` component showing MCP server name, tool name, and status (pending/succeeded/failed) for each invocation
    - Create `TraceViewer` component showing sequence of agent reasoning steps and tool calls with timing data
    - Display trace view within 3 seconds of request completion
    - Display error message indicating which MCP server/tool failed when agent encounters error
    - _Requirements: 5.4, 5.6, 9.2_

  - [x] 11.3 Implement conversation sidebar and management
    - Create `ConversationSidebar` component listing previous conversations ordered by most recent activity (max 50)
    - Implement "New Conversation" button that starts fresh context without prior history
    - Preserve previous conversations in sidebar when starting new conversation
    - Load conversation history on sign-in
    - _Requirements: 10.3, 10.4_

- [x] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Implement Infrastructure Configuration
  - [x] 13.1 Create CloudFront distribution configuration
    - Create IaC template (CloudFormation/CDK) for CloudFront distribution
    - Configure TLS termination with publicly trusted certificate for www.awsteach.com (minimum TLS 1.2)
    - Configure edge caching for static assets with cache-control max-age 86400 seconds
    - Configure `/api/*` path forwarding to EC2 origin
    - Configure HTTP to HTTPS 301 redirect
    - Configure 30-second timeout for origin responses on 5xx errors
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 13.2 Create Route 53 DNS configuration
    - Create A-type alias records for `www.awsteach.com` and `awsteach.com` (apex) pointing to CloudFront distribution
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 13.3 Create Cognito user pool configuration
    - Create Cognito user pool with email verification, password policy, 60-minute session token lifetime
    - Configure account lockout: 5 failed attempts, 15-minute lock duration
    - Configure display name attribute (2-50 chars)
    - _Requirements: 1.2, 2.1, 2.4_

  - [x] 13.4 Create DynamoDB table configuration
    - Create `agentcore-demo-conversations` table with single-table design
    - Configure PK (`USER#{user_id}`), SK (`CONV#{conversation_id}` or `MSG#{message_id}`)
    - Create GSI1 (PK: `USER#{user_id}`, SK: `UPDATED#{updated_at}`)
    - Enable TTL attribute
    - _Requirements: 10.1, 10.3, 10.5_

  - [x] 13.5 Create systemd service configurations for EC2 deployment
    - Create systemd unit files for: backend API (port 8000), Financial Research MCP (port 8001), Knowledge Base MCP (port 8002), Agent runtime
    - Configure `RestartSec=10` for auto-restart on crash
    - Configure `StartLimitBurst=5` and `StartLimitIntervalSec=60` for restart limits
    - Configure service dependencies (MCP servers start before agent runtime)
    - Add health check endpoints for systemd watchdog monitoring
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 14. Wire components together and integration
  - [x] 14.1 Connect frontend to backend API
    - Configure API base URL and authentication header injection
    - Implement request/response interceptors for token refresh and error handling
    - Connect chat interface to `POST /api/chat/message` endpoint
    - Connect conversation sidebar to `GET /api/chat/conversations` endpoint
    - Connect trace viewer to `GET /api/chat/trace/{request_id}` endpoint
    - _Requirements: 5.1, 5.4, 9.2, 10.3_

  - [x] 14.2 Wire agent runtime to backend API
    - Integrate agent invocation into chat message endpoint
    - Pass tool invocation details and trace data from agent to API response
    - Implement response streaming from agent to frontend
    - Handle agent timeout (30s) at API level
    - _Requirements: 5.1, 5.3, 5.5, 5.7_

  - [x] 14.3 Write integration tests
    - Test full registration and sign-in flow against mocked Cognito
    - Test chat message flow from API through agent to MCP servers (mocked Bedrock)
    - Test conversation CRUD operations against mocked DynamoDB
    - Test MCP server health endpoints
    - Test service startup sequence
    - _Requirements: 1.2, 2.1, 5.1, 8.3, 10.1_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python 3.12 with FastAPI; frontend uses React 18 with TypeScript
- Property-based tests use Hypothesis (Python) with minimum 100 iterations per property
- Local development uses moto for DynamoDB/Cognito mocking and httpx mock for MCP servers

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "10.1"] },
    { "id": 2, "tasks": ["1.3", "2.1", "4.1", "5.1", "13.1", "13.2", "13.3", "13.4", "13.5"] },
    { "id": 3, "tasks": ["1.4", "2.2", "2.3", "4.2", "5.2"] },
    { "id": 4, "tasks": ["2.4", "2.5", "4.3", "5.3", "10.2", "10.3"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "11.1"] },
    { "id": 8, "tasks": ["11.2", "11.3"] },
    { "id": 9, "tasks": ["14.1", "14.2"] },
    { "id": 10, "tasks": ["14.3"] }
  ]
}
```
