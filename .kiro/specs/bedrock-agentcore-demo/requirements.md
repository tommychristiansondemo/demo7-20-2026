# Requirements Document

## Introduction

This document specifies the requirements for a demo application used in a one-day AWS class titled "Building Agentic AI with Amazon Bedrock AgentCore," taught to employees of Ameriprise Financial. The application demonstrates real-world agentic AI patterns using Amazon Bedrock AgentCore technologies, the Strands Agents framework, and MCP (Model Context Protocol) servers. Students interact with the application through a web portal at https://www.awsteach.com, authenticating via Amazon Cognito, with content delivered through CloudFront CDN. The application runs on an EC2 instance with full administrative IAM role access in the instructor's AWS account.

## Glossary

- **Portal**: The web-based user interface served at https://www.awsteach.com where students register, sign in, and interact with the agentic AI demo features.
- **MCP_Server**: A Model Context Protocol server built with the Strands Agents framework that exposes tools and resources to AI agents, enabling structured interaction with external services.
- **Agent**: An AI-powered conversational entity backed by Amazon Bedrock foundation models that uses MCP_Servers to perform actions on behalf of users.
- **Strands_Framework**: The Strands Agents SDK, an open-source Python framework for building AI agents that can use tools, including MCP server integrations.
- **AgentCore**: Amazon Bedrock AgentCore, a set of managed services for deploying, securing, and observing AI agents in production.
- **Cognito**: Amazon Cognito, the AWS service used for user authentication, registration, and session management.
- **CloudFront**: Amazon CloudFront, the AWS CDN service used to deliver the Portal's static assets and API traffic with low latency and HTTPS termination.
- **EC2_Instance**: The Amazon EC2 virtual machine hosting the application backend, MCP_Servers, and Agent runtime, configured with an administrative IAM role.
- **Student**: An employee of Ameriprise Financial attending the one-day class who registers and uses the Portal.
- **Financial_Research_MCP**: An MCP_Server that provides tools for retrieving and analyzing financial market data, demonstrating real-world agentic AI applied to financial services.
- **Knowledge_Base_MCP**: An MCP_Server that provides tools for querying a knowledge base of AWS documentation and course materials, demonstrating retrieval-augmented generation patterns.

## Requirements

### Requirement 1: User Registration

**User Story:** As a Student, I want to register for an account on the Portal, so that I can access the agentic AI demo features during the class.

#### Acceptance Criteria

1. WHEN a Student navigates to the Portal registration page, THE Portal SHALL display a registration form requesting email address, password, and display name.
2. WHEN a Student submits a registration form where the email address is a valid email format, the password meets Cognito password policy, and the display name is between 2 and 50 characters, THE Portal SHALL create a new user account in Cognito and send a verification code to the provided email address.
3. WHEN a Student provides a valid verification code within 24 hours of registration, THE Portal SHALL confirm the account and redirect the Student to the sign-in page.
4. IF a Student submits a registration form with an email already registered in Cognito, THEN THE Portal SHALL display an error message indicating the email is already in use.
5. IF a Student submits a registration form with a password that does not meet Cognito password policy, THEN THE Portal SHALL display an error message listing the unmet password requirements.
6. IF a Student submits a registration form with a display name shorter than 2 characters or longer than 50 characters, THEN THE Portal SHALL display an error message indicating the display name must be between 2 and 50 characters.
7. IF a Student provides an invalid or expired verification code, THEN THE Portal SHALL display an error message indicating the code is invalid or expired and offer an option to resend the verification code.
8. IF a Student submits a registration form with an email address that is not in valid email format, THEN THE Portal SHALL display an error message indicating the email format is invalid.

### Requirement 2: User Authentication

**User Story:** As a Student, I want to sign in to the Portal, so that I can access the demo features in a personalized session.

#### Acceptance Criteria

1. WHEN a Student provides valid credentials (email and password) on the sign-in page, THE Portal SHALL authenticate the Student via Cognito and issue a session token with a lifetime of 60 minutes.
2. WHEN a Student is successfully authenticated, THE Portal SHALL redirect the Student to the main dashboard.
3. IF a Student provides invalid credentials, THEN THE Portal SHALL display a generic error message indicating that the sign-in failed without revealing whether the email or password was incorrect.
4. IF a Student fails authentication 5 consecutive times for the same email address, THEN THE Portal SHALL lock the account for 15 minutes and display a message indicating the account is temporarily locked.
5. WHEN a Student clicks the sign-out button, THE Portal SHALL invalidate the session token and redirect to the sign-in page.
6. WHILE a Student session token is expired, THE Portal SHALL redirect all authenticated requests to the sign-in page.
7. IF Cognito is unavailable during a sign-in attempt, THEN THE Portal SHALL display an error message indicating the service is temporarily unavailable and prompt the Student to retry.

### Requirement 3: Financial Research MCP Server

**User Story:** As a Student, I want to interact with a financial research agent, so that I can see how agentic AI retrieves and analyzes financial market data in a real-world scenario relevant to Ameriprise Financial.

#### Acceptance Criteria

1. THE Financial_Research_MCP SHALL expose tools for retrieving stock quotes, company profiles, and market summaries via the Model Context Protocol, where market summaries include major index values, daily change percentages, and top gaining and losing ticker symbols.
2. THE Financial_Research_MCP SHALL be implemented using the Strands_Framework.
3. WHEN the Agent invokes a stock quote tool on the Financial_Research_MCP, THE Financial_Research_MCP SHALL return current price, change percentage, and volume for the requested ticker symbol.
4. WHEN the Agent invokes a company profile tool on the Financial_Research_MCP, THE Financial_Research_MCP SHALL return company name, sector, market capitalization, and a description of no more than 500 characters.
5. IF the Financial_Research_MCP receives a request for an invalid ticker symbol, THEN THE Financial_Research_MCP SHALL return an error response containing an error type and a descriptive message indicating the symbol was not found.
6. THE Financial_Research_MCP SHALL register with AgentCore for discoverability and management.
7. IF the Financial_Research_MCP cannot reach its external financial data source, THEN THE Financial_Research_MCP SHALL return an error response containing an error type and a descriptive message indicating the data source is unavailable.

### Requirement 4: Knowledge Base MCP Server

**User Story:** As a Student, I want to ask questions about AWS services and course materials, so that I can see how agentic AI performs retrieval-augmented generation using a knowledge base.

#### Acceptance Criteria

1. THE Knowledge_Base_MCP SHALL expose tools for querying a knowledge base of AWS Bedrock AgentCore documentation and course-related materials via the Model Context Protocol.
2. THE Knowledge_Base_MCP SHALL be implemented using the Strands_Framework.
3. WHEN the Agent invokes a query tool on the Knowledge_Base_MCP, THE Knowledge_Base_MCP SHALL return up to 5 passages, each including the passage text, a source document title, and a section identifier indicating where the passage originated.
4. WHEN the Agent invokes a query tool, THE Knowledge_Base_MCP SHALL include a relevance score between 0.0 and 1.0 for each returned passage, and SHALL only return passages with a relevance score at or above 0.3.
5. IF the Knowledge_Base_MCP receives a query where no passages meet the minimum relevance score of 0.3, THEN THE Knowledge_Base_MCP SHALL return an empty result set with a message indicating no matching content was found.
6. THE Knowledge_Base_MCP SHALL register with AgentCore for discoverability and management.
7. IF the Knowledge_Base_MCP receives a query that is empty or exceeds 1000 characters, THEN THE Knowledge_Base_MCP SHALL return a structured error indicating the query is invalid.

### Requirement 5: Conversational Agent Interface

**User Story:** As a Student, I want to have a natural language conversation with an AI agent that can use multiple tools, so that I can experience how agentic AI orchestrates actions across MCP servers.

#### Acceptance Criteria

1. WHEN a Student sends a message of 1 to 2000 characters through the Portal chat interface, THE Agent SHALL process the message using an Amazon Bedrock foundation model and return a natural language response.
2. THE Agent SHALL have access to both the Financial_Research_MCP and the Knowledge_Base_MCP for tool invocation.
3. WHEN the Agent determines a tool call is needed, THE Agent SHALL invoke the appropriate MCP_Server tool, incorporate the result into the response, and complete the request using no more than 10 tool invocations per student message.
4. WHEN the Agent invokes a tool, THE Portal SHALL display the tool invocation details to the Student including the MCP_Server name, the tool name, and the invocation status (pending, succeeded, or failed).
5. WHILE the Agent is processing a request, THE Portal SHALL display a loading indicator to the Student until the response is complete or 30 seconds have elapsed.
6. IF the Agent encounters an error from an MCP_Server, THEN THE Agent SHALL display an error message to the Student indicating which MCP_Server and tool failed, and suggest that the Student rephrase the request or ask a different question.
7. IF the Agent does not complete processing within 30 seconds, THEN THE Portal SHALL stop the loading indicator and display a timeout message indicating the request could not be completed.
8. IF a Student submits an empty message or a message exceeding 2000 characters, THEN THE Portal SHALL reject the submission and display a validation message indicating the allowed message length.

### Requirement 6: CloudFront Content Delivery

**User Story:** As a Student, I want the Portal to load quickly and securely, so that I can focus on the course material without delays.

#### Acceptance Criteria

1. THE CloudFront distribution SHALL serve the Portal static assets (HTML, CSS, JavaScript) from an edge cache.
2. THE CloudFront distribution SHALL terminate TLS using a publicly trusted certificate that matches the domain www.awsteach.com and enforce a minimum TLS version of 1.2.
3. THE CloudFront distribution SHALL forward API requests (path prefix /api/*) to the EC2_Instance origin.
4. WHEN a Student accesses http://www.awsteach.com, THE CloudFront distribution SHALL return a 301 permanent redirect to https://www.awsteach.com.
5. THE CloudFront distribution SHALL set the cache-control header for static assets to a maximum age of 86400 seconds.
6. IF the EC2_Instance origin is unreachable or returns a 5xx error for an /api/* request, THEN THE CloudFront distribution SHALL return an error response to the Student within 30 seconds.

### Requirement 7: DNS Configuration

**User Story:** As the instructor, I want the Portal accessible at www.awsteach.com, so that students have a clean, memorable URL.

#### Acceptance Criteria

1. THE Route_53 hosted zone for awsteach.com SHALL contain an A-type alias record for www.awsteach.com pointing to the CloudFront distribution.
2. WHEN a Student resolves www.awsteach.com, THE DNS resolution SHALL return an address that belongs to the CloudFront distribution within 5 seconds.
3. THE Route_53 hosted zone SHALL contain an A-type alias record for awsteach.com (apex) pointing to the CloudFront distribution.
4. WHEN a Student resolves awsteach.com (apex), THE DNS resolution SHALL return an address that belongs to the CloudFront distribution within 5 seconds.

### Requirement 8: Application Deployment on EC2

**User Story:** As the instructor, I want the entire backend deployed on a single EC2 instance, so that the demo is simple to set up and tear down for the class.

#### Acceptance Criteria

1. THE EC2_Instance SHALL host the Agent runtime, both MCP_Servers (Financial_Research_MCP and Knowledge_Base_MCP), and the backend API on a single machine.
2. THE EC2_Instance SHALL use the administrative IAM role to access AWS services including Bedrock, Cognito, and Route 53.
3. WHEN the EC2_Instance reaches the running state, THE process manager SHALL start the Agent runtime, Financial_Research_MCP, Knowledge_Base_MCP, and backend API within 120 seconds, each service accepting connections on its configured port without manual intervention.
4. IF any application service on the EC2_Instance crashes, THEN the process manager SHALL restart the failed service within 10 seconds, up to a maximum of 5 consecutive restart attempts within a 60-second window.
5. IF an application service exceeds its maximum restart attempts within the restart window, THEN the process manager SHALL stop attempting to restart that service and log an error indicating the service has entered a failed state.

### Requirement 9: Agent Observability

**User Story:** As a Student, I want to see how agent actions are traced and monitored, so that I can understand production observability patterns for agentic AI.

#### Acceptance Criteria

1. THE Agent SHALL emit a trace span for each tool invocation, including MCP_Server name, tool name, duration in milliseconds, and a success or failure status.
2. WHEN a Student views the conversation history, THE Portal SHALL display a trace view showing the sequence of agent reasoning steps and tool calls within 3 seconds of the request.
3. THE Agent SHALL log each user message, each LLM inference call, and each tool invocation using AgentCore observability features.
4. WHEN an Agent request completes, THE observability data SHALL include total latency in milliseconds, number of tool calls, prompt token count, and completion token count.
5. IF the Agent fails to emit a trace span or log an interaction, THEN THE Agent SHALL continue processing the request and record the observability failure in a fallback log entry.

### Requirement 10: Session and Conversation Management

**User Story:** As a Student, I want my conversation history preserved during the class, so that I can review previous interactions.

#### Acceptance Criteria

1. WHEN a Student sends a message, THE Portal SHALL persist the message and the Agent response in the conversation history in chronological order, supporting messages up to 2000 characters in length.
2. IF a message fails to persist, THEN THE Portal SHALL display an error message indicating the failure and SHALL retain the unsent message text in the input field so the Student can retry.
3. WHEN a Student returns to the Portal after signing in, THE Portal SHALL display the Student's previous conversations in the sidebar list ordered by most recent activity, showing up to 50 most recent conversations.
4. WHEN a Student clicks "New Conversation," THE Portal SHALL start a fresh conversation context with no prior message history loaded, while preserving previous conversations in the sidebar list.
5. THE Portal SHALL store conversation history associated with the authenticated Student identity from Cognito and retain it for the duration of the Student's course enrollment.
