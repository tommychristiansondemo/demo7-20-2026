import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TraceViewer } from "./TraceViewer";
import { configureApiClient } from "@/api/client";

// Mock useAuth
vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    sessionToken: "mock-token-123",
  }),
}));

const mockTraceResponse = {
  request_id: "req-001",
  trace: {
    total_latency_ms: 1200,
    tool_call_count: 2,
    prompt_tokens: 500,
    completion_tokens: 200,
    spans: [
      {
        name: "LLM Inference",
        mcp_server: null,
        tool_name: null,
        duration_ms: 800,
        status: "success" as const,
      },
      {
        name: "Tool Call: get_stock_quote",
        mcp_server: "Financial_Research",
        tool_name: "get_stock_quote",
        duration_ms: 350,
        status: "success" as const,
      },
      {
        name: "Tool Call: query_knowledge_base",
        mcp_server: "Knowledge_Base",
        tool_name: "query_knowledge_base",
        duration_ms: 50,
        status: "failure" as const,
      },
    ],
  },
  tool_invocations: [
    { mcp_server: "Financial_Research", tool_name: "get_stock_quote", status: "succeeded", duration_ms: 350 },
    { mcp_server: "Knowledge_Base", tool_name: "query_knowledge_base", status: "failed", duration_ms: 50 },
  ],
};

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("TraceViewer", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    configureApiClient({
      baseUrl: "/api",
      getSessionToken: () => "mock-token-123",
      onUnauthorized: () => {},
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows loading state initially", () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    render(<TraceViewer requestId="req-001" />);
    expect(screen.getByText("Loading trace data...")).toBeInTheDocument();
  });

  it("fetches trace data from correct endpoint", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockTraceResponse,
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/chat/trace/req-001",
        expect.objectContaining({
          method: "GET",
          headers: expect.objectContaining({
            Authorization: "Bearer mock-token-123",
          }),
        })
      );
    });
  });

  it("displays trace summary with latency, tool calls, and tokens", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockTraceResponse,
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(screen.getByText("Latency: 1200ms")).toBeInTheDocument();
    });
    expect(screen.getByText("Tool calls: 2")).toBeInTheDocument();
    expect(screen.getByText("Tokens: 700")).toBeInTheDocument();
  });

  it("displays trace spans with names and durations", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockTraceResponse,
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(screen.getByText("LLM Inference")).toBeInTheDocument();
    });
    expect(screen.getByText("Tool Call: get_stock_quote")).toBeInTheDocument();
    expect(screen.getByText("Tool Call: query_knowledge_base")).toBeInTheDocument();

    expect(screen.getByText("800ms")).toBeInTheDocument();
    expect(screen.getByText("350ms")).toBeInTheDocument();
    expect(screen.getByText("50ms")).toBeInTheDocument();
  });

  it("displays MCP server and tool name for tool call spans", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockTraceResponse,
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(screen.getByText("Financial_Research/get_stock_quote")).toBeInTheDocument();
    });
    expect(screen.getByText("Knowledge_Base/query_knowledge_base")).toBeInTheDocument();
  });

  it("shows success and failure status badges for spans", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockTraceResponse,
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(screen.getAllByText("OK")).toHaveLength(2);
    });
    expect(screen.getByText("FAIL")).toBeInTheDocument();
  });

  it("displays token usage in footer", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockTraceResponse,
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(screen.getByText("Prompt: 500 tokens")).toBeInTheDocument();
    });
    expect(screen.getByText("Completion: 200 tokens")).toBeInTheDocument();
  });

  it("displays error when fetch fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ message: "Internal server error" }),
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(
        screen.getByText("Internal server error")
      ).toBeInTheDocument();
    });
  });

  it("calls onError callback when fetch fails", async () => {
    const onError = vi.fn();
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ message: "Trace not found" }),
    });

    render(<TraceViewer requestId="req-001" onError={onError} />);

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith("Trace not found");
    });
  });

  it("shows retry button on error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ message: "Server error" }),
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(screen.getByText("Retry")).toBeInTheDocument();
    });
  });

  it("displays percentage of total latency for each span", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockTraceResponse,
    });

    render(<TraceViewer requestId="req-001" />);

    // 800/1200 = 67%, 350/1200 = 29%, 50/1200 = 4%
    await waitFor(() => {
      expect(screen.getByText("(67%)")).toBeInTheDocument();
    });
    expect(screen.getByText("(29%)")).toBeInTheDocument();
    expect(screen.getByText("(4%)")).toBeInTheDocument();
  });

  it("handles empty spans array", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        ...mockTraceResponse,
        trace: { ...mockTraceResponse.trace, spans: [] },
      }),
    });

    render(<TraceViewer requestId="req-001" />);

    await waitFor(() => {
      expect(screen.getByText("No trace spans recorded.")).toBeInTheDocument();
    });
  });

  it("has accessible aria-label", () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));
    render(<TraceViewer requestId="req-001" />);
    expect(screen.getByLabelText("Trace viewer")).toBeInTheDocument();
  });
});
