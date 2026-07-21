# Implementation Plan: Observability Dashboard

## Overview

This plan implements a shared observability dashboard at `/observe` that displays the last 10 inference requests across all students, with drill-down into extended thinking content. The implementation proceeds backend-first (utility functions → DynamoDB client → API router → agent integration) then wires up the React frontend, finishing with integration wiring.

## Tasks

- [ ] 1. Create utility functions and data models
  - [ ] 1.1 Create the message preview truncation utility
    - Create `backend/utils/__init__.py` and `backend/utils/truncate.py`
    - Implement `truncate_message(message: str, max_length: int = 100) -> str`
    - If message length ≤ max_length, return original; otherwise return first max_length chars + "..."
    - _Requirements: 3.1, 3.2_

  - [ ]* 1.2 Write property test for message preview truncation
    - **Property 4: Message preview truncation**
    - Use Hypothesis to generate random strings (0–500 chars)
    - Verify: messages ≤ 100 chars return unchanged; messages > 100 chars return first 100 + "..."
    - Create `tests/test_truncate_properties.py`
    - **Validates: Requirements 3.1, 3.2**

  - [ ] 1.3 Create the average latency computation function
    - Add `compute_average_latency(records: list) -> float` in `backend/utils/truncate.py` or a new `backend/utils/metrics.py`
    - Return 0.0 for empty list; arithmetic mean of `total_latency_ms` values otherwise
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 1.4 Write property test for average latency computation
    - **Property 6: Average latency computation correctness**
    - Use Hypothesis to generate lists of non-negative floats
    - Verify: empty list → 0.0; non-empty → sum/count within floating point tolerance
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [ ] 2. Implement telemetry DynamoDB client
  - [ ] 2.1 Create the TelemetryDBClient class
    - Create `backend/db/telemetry.py`
    - Define `TelemetryRecord` dataclass with fields: `record_id`, `student_email`, `message_preview`, `total_latency_ms`, `tool_call_count`, `timestamp`, `thinking_content`
    - Implement `TelemetryDBClient` with `__init__` accepting optional `table_name` and `endpoint_url`
    - Table name: `agentcore-demo-telemetry`, PK always `"TELEMETRY"`, SK `"{timestamp}#{record_id}"`
    - _Requirements: 7.1, 7.2_

  - [ ] 2.2 Implement `put_record` with rolling window enforcement
    - Query all records (PK = "TELEMETRY"), count them
    - If count ≥ 10, delete the item with the lowest SK (oldest timestamp)
    - Put the new record
    - _Requirements: 7.2, 7.3, 2.3_

  - [ ] 2.3 Implement `get_feed` and `get_thinking` methods
    - `get_feed()`: Query PK = "TELEMETRY", ScanIndexForward=False, return all records ordered by timestamp descending
    - `get_thinking(record_id)`: Scan or query for the record matching `record_id`, return `thinking_content`
    - _Requirements: 2.2, 4.2_

  - [ ]* 2.4 Write property test for rolling window size invariant
    - **Property 1: Rolling window size invariant**
    - Use Hypothesis to generate sequences of 1–20 TelemetryRecord insertions
    - After each insertion, verify table contains at most 10 records
    - Use DynamoDB Local or moto for testing
    - **Validates: Requirements 2.3, 7.2, 7.3, 8.3**

  - [ ]* 2.5 Write property test for feed ordering
    - **Property 2: Feed ordering by timestamp descending**
    - Generate random sets of records with distinct timestamps, insert them, call `get_feed()`
    - Verify consecutive records satisfy `records[i].timestamp >= records[i+1].timestamp`
    - **Validates: Requirements 2.2**

  - [ ]* 2.6 Write property test for telemetry persistence round-trip
    - **Property 7: Telemetry persistence round-trip**
    - Generate random valid TelemetryRecords, write to DynamoDB, read back via `get_feed()`
    - Verify all fields match: `record_id`, `student_email`, `message_preview`, `total_latency_ms`, `tool_call_count`, `timestamp`, `thinking_content`
    - **Validates: Requirements 7.1**

- [ ] 3. Checkpoint - Backend data layer complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement observe API router
  - [ ] 4.1 Create the observe API router with authentication
    - Create `backend/api/observe.py`
    - Define `GET /api/observe/feed` endpoint requiring valid Cognito token via `get_current_user` dependency
    - Define `GET /api/observe/thinking/{record_id}` endpoint requiring valid Cognito token
    - Return HTTP 401 with redirect hint for invalid/expired tokens
    - _Requirements: 1.3, 1.4_

  - [ ] 4.2 Implement feed endpoint response
    - Instantiate `TelemetryDBClient`, call `get_feed()`
    - Compute `average_latency_ms` using `compute_average_latency`
    - Return `TelemetryFeedResponse` with records (excluding `thinking_content`) and average latency
    - Define Pydantic models: `TelemetryFeedItem`, `TelemetryFeedResponse`
    - _Requirements: 2.1, 2.2, 2.4, 6.1, 6.3, 8.1_

  - [ ] 4.3 Implement thinking endpoint
    - Call `TelemetryDBClient.get_thinking(record_id)`
    - Return `ThinkingResponse` with `record_id`, `thinking_content`, and `has_thinking` boolean
    - Return HTTP 404 if record not found
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 4.4 Register observe router in the FastAPI app
    - Import and include the observe router in `backend/api/__init__.py`
    - _Requirements: 1.3_

  - [ ]* 4.5 Write unit tests for observe API endpoints
    - Test feed endpoint returns correct structure with mocked TelemetryDBClient
    - Test thinking endpoint returns content or 404
    - Test authentication enforcement (401 without token)
    - Create `tests/test_observe_api.py`
    - _Requirements: 1.3, 1.4, 2.2, 4.2, 4.3_

- [ ] 5. Enable extended thinking and telemetry capture
  - [ ] 5.1 Enable extended thinking on the Bedrock model
    - Modify `_create_model()` in `agent/runtime.py` to add `model_kwargs={"thinking": {"type": "enabled", "budget_tokens": 5000}}`
    - _Requirements: 5.1_

  - [ ] 5.2 Implement thinking content extraction
    - Add `extract_thinking_content(result) -> str` function in `agent/runtime.py`
    - Iterate through `result.message["content"]` blocks, collect blocks with `type == "thinking"`
    - Return concatenated thinking text, or empty string if none found
    - Add `thinking_content` field to `AgentResponse` dataclass
    - Populate `thinking_content` in `process_message` after agent completes
    - _Requirements: 5.2, 5.3_

  - [ ]* 5.3 Write property test for thinking content extraction
    - **Property 5: Thinking content extraction preservation**
    - Use Hypothesis to generate mock response dicts with 0–5 thinking blocks
    - Verify: responses with thinking blocks → extracted text contains all blocks; no thinking blocks → empty string
    - Create `tests/test_thinking_extraction_properties.py`
    - **Validates: Requirements 5.2, 5.3**

  - [ ] 5.4 Integrate telemetry capture into chat message flow
    - In `backend/api/chat.py`, after the agent responds, call a `_capture_telemetry` helper
    - The helper creates a `TelemetryRecord` with: student email from `user.email`, message preview (truncated), total latency from `agent_response.trace.total_latency_ms`, tool call count from `agent_response.trace.tool_call_count`, current timestamp, and thinking content
    - Wrap in try/except: log warning on failure, never interrupt user response
    - Handle timeout case: record with timeout latency and zero tool calls
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 5.5 Write unit tests for telemetry capture resilience
    - Test that DynamoDB write failure does not raise exception in send_message
    - Test that telemetry record is created with correct fields on success
    - Test timeout case creates record with appropriate values
    - _Requirements: 9.3_

- [ ] 6. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement frontend observe page
  - [ ] 7.1 Create the ObservePage component with routing
    - Create `frontend/src/pages/ObservePage.tsx`
    - Add `/observe` route to `App.tsx` wrapped in `<RouteGuard>` (same pattern as `/dashboard` and `/chat`)
    - Export `ObservePage` from `frontend/src/pages/index.ts`
    - Show loading state while fetching feed data
    - _Requirements: 1.1, 1.2_

  - [ ] 7.2 Implement the telemetry feed table
    - Fetch `GET /api/observe/feed` on page load using the existing API client pattern
    - Display table with columns: Student Email, Message Preview, Latency (ms), Tool Calls, Timestamp
    - Order by timestamp descending (as returned by API)
    - Show "No inference activity yet" when records list is empty
    - _Requirements: 2.1, 2.4, 3.1, 8.2_

  - [ ] 7.3 Implement the average latency card
    - Display `average_latency_ms` from the feed response in a summary card above the table
    - Format as "Avg Latency: X ms" with reasonable precision (1 decimal place)
    - Show "0 ms" when no records exist
    - _Requirements: 6.1, 6.2_

  - [ ] 7.4 Implement the thinking drill-down panel
    - Make each table row clickable/selectable
    - On selection, fetch `GET /api/observe/thinking/{record_id}`
    - Display thinking content in a panel/modal below the table or as a slide-over
    - Show "No reasoning chain available" when `has_thinking` is false
    - _Requirements: 4.1, 4.3_

  - [ ]* 7.5 Write frontend unit tests
    - Test ObservePage renders table with mocked feed data (Vitest + React Testing Library)
    - Test LatencyCard displays formatted average
    - Test ThinkingPanel shows content or "no reasoning available" message
    - Test empty state renders correctly
    - Create `frontend/src/pages/__tests__/ObservePage.test.tsx`
    - _Requirements: 2.1, 4.3, 6.1_

- [ ] 8. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The backend uses Python (FastAPI, pytest, Hypothesis) and the frontend uses TypeScript (React, Vitest)
- DynamoDB Local or moto can be used for property tests against the telemetry table

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "2.1"] },
    { "id": 1, "tasks": ["1.2", "1.4", "2.2", "2.3"] },
    { "id": 2, "tasks": ["2.4", "2.5", "2.6", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "4.4", "5.1", "5.2"] },
    { "id": 4, "tasks": ["4.5", "5.3", "5.4"] },
    { "id": 5, "tasks": ["5.5", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3"] },
    { "id": 7, "tasks": ["7.4", "7.5"] }
  ]
}
```
