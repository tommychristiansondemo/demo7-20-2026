# Requirements Document

## Introduction

The Observability Dashboard feature adds a shared, supervisory view at `/observe` that displays the last 10 inference requests across all students in the Bedrock AgentCore demo application. It enables participants to see real-time activity, inspect chain-of-thought reasoning via extended thinking, and monitor rolling average latency. Telemetry data persists in DynamoDB so the dashboard survives application restarts.

## Glossary

- **Dashboard**: The observability page rendered at the `/observe` route that displays inference telemetry for all students.
- **Inference_Request**: A single user-to-agent message exchange that produces a response, including associated telemetry (latency, tool calls, thinking chain).
- **Telemetry_Record**: A DynamoDB item storing metadata about a single Inference_Request, including student email, message preview, latency, tool call count, timestamp, and extended thinking content.
- **Rolling_Window**: A fixed-size collection of the 10 most recent Telemetry_Records; when an 11th record arrives, the oldest record is evicted.
- **Extended_Thinking**: The chain-of-thought reasoning produced by Claude when the Bedrock `thinking` parameter is enabled, capturing the model's internal deliberation before generating a response.
- **Backend_API**: The FastAPI application serving REST endpoints under `/api`.
- **Frontend_App**: The React single-page application rendering protected routes.
- **Telemetry_Table**: The DynamoDB table storing Telemetry_Records for the observability dashboard.
- **Average_Latency**: The arithmetic mean of total_latency_ms values across all Telemetry_Records currently in the Rolling_Window.

## Requirements

### Requirement 1: Protected Dashboard Route

**User Story:** As a student, I want the observability dashboard to require authentication, so that only enrolled participants can view inference activity.

#### Acceptance Criteria

1. WHEN an unauthenticated user navigates to `/observe`, THE Frontend_App SHALL redirect the user to the sign-in page.
2. WHEN an authenticated user navigates to `/observe`, THE Frontend_App SHALL render the Dashboard.
3. THE Backend_API SHALL require a valid Cognito access token for all observability endpoints.
4. IF an observability API request contains an invalid or expired token, THEN THE Backend_API SHALL return HTTP 401 with a redirect hint to the sign-in page.

### Requirement 2: Global Inference Request List

**User Story:** As a student, I want to see the last 10 inference requests from all students, so that I can observe how others are using the agent.

#### Acceptance Criteria

1. WHEN the Dashboard loads, THE Frontend_App SHALL display the 10 most recent Inference_Requests across all students.
2. THE Backend_API SHALL provide an endpoint that returns the current Rolling_Window of Telemetry_Records ordered by timestamp descending.
3. WHEN a new Inference_Request completes and the Rolling_Window already contains 10 records, THE Backend_API SHALL evict the oldest Telemetry_Record before storing the new one.
4. THE Dashboard SHALL display each Inference_Request with the student email, a message preview, total latency in milliseconds, tool call count, and timestamp.

### Requirement 3: Message Preview Display

**User Story:** As a student, I want to see a preview of each inference request message, so that I can understand what question was asked without seeing the full content.

#### Acceptance Criteria

1. THE Dashboard SHALL display a message preview of up to 100 characters for each Inference_Request.
2. WHEN the original message exceeds 100 characters, THE Dashboard SHALL truncate the preview and append an ellipsis indicator.

### Requirement 4: Drill-Down Extended Thinking View

**User Story:** As a student, I want to drill down on a request to see the model's reasoning chain, so that I can understand how the agent arrived at its answer.

#### Acceptance Criteria

1. WHEN a user selects an Inference_Request in the Dashboard, THE Frontend_App SHALL display the Extended_Thinking content for that request.
2. THE Backend_API SHALL provide an endpoint that returns the Extended_Thinking content for a specific Telemetry_Record.
3. IF a Telemetry_Record has no Extended_Thinking content, THEN THE Dashboard SHALL display a message indicating no reasoning chain is available.

### Requirement 5: Extended Thinking Enablement

**User Story:** As a developer, I want the agent to use Bedrock extended thinking, so that the chain-of-thought reasoning is captured for observability.

#### Acceptance Criteria

1. THE Backend_API SHALL invoke the `us.anthropic.claude-sonnet-4-6` model via Bedrock with the `thinking` parameter enabled.
2. WHEN the model returns a response with thinking content, THE Backend_API SHALL extract and store the thinking content in the Telemetry_Record.
3. IF the model response does not include thinking content, THEN THE Backend_API SHALL store an empty thinking field in the Telemetry_Record.

### Requirement 6: Rolling Average Latency

**User Story:** As a student, I want to see the rolling average latency, so that I can gauge the typical response time of the agent.

#### Acceptance Criteria

1. THE Dashboard SHALL display the Average_Latency computed from all Telemetry_Records in the current Rolling_Window.
2. WHEN the Rolling_Window contains zero records, THE Dashboard SHALL display the Average_Latency as zero.
3. WHEN a new Telemetry_Record is added or the oldest is evicted, THE Backend_API SHALL recompute the Average_Latency and include it in the observability endpoint response.

### Requirement 7: DynamoDB Telemetry Persistence

**User Story:** As a developer, I want inference telemetry stored in DynamoDB, so that the dashboard data persists across application restarts.

#### Acceptance Criteria

1. THE Backend_API SHALL store each Telemetry_Record in the Telemetry_Table in DynamoDB.
2. THE Telemetry_Table SHALL retain a maximum of 10 Telemetry_Records at any time.
3. WHEN the Telemetry_Table contains 10 records and a new Inference_Request completes, THE Backend_API SHALL delete the oldest record before inserting the new one.
4. WHEN the Backend_API starts, THE Backend_API SHALL read existing Telemetry_Records from the Telemetry_Table to populate the Dashboard.

### Requirement 8: Shared Supervisory View

**User Story:** As a student, I want to see all other students' inference activity, so that I can learn from their interactions and monitor class usage.

#### Acceptance Criteria

1. THE Backend_API SHALL return Telemetry_Records from all students regardless of which authenticated user makes the request.
2. THE Dashboard SHALL display the student email associated with each Inference_Request so viewers can identify who sent it.
3. THE Dashboard SHALL enforce a maximum display of 10 Inference_Requests to protect student privacy.

### Requirement 9: Telemetry Capture on Inference Completion

**User Story:** As a developer, I want telemetry captured automatically when an inference completes, so that the dashboard stays current without manual intervention.

#### Acceptance Criteria

1. WHEN an Inference_Request completes successfully, THE Backend_API SHALL create a Telemetry_Record containing the student email, message preview, total latency, tool call count, timestamp, and Extended_Thinking content.
2. WHEN an Inference_Request times out, THE Backend_API SHALL create a Telemetry_Record with the timeout latency and zero tool calls.
3. IF writing the Telemetry_Record to DynamoDB fails, THEN THE Backend_API SHALL log the failure and continue processing the user response without interruption.
