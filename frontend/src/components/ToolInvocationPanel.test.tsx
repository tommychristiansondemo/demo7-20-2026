import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolInvocationPanel, ToolInvocation } from "./ToolInvocationPanel";

describe("ToolInvocationPanel", () => {
  it("renders nothing when invocations list is empty", () => {
    const { container } = render(<ToolInvocationPanel invocations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("displays MCP server name and tool name for each invocation", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "Financial_Research", tool_name: "get_stock_quote", status: "succeeded" },
      { mcp_server: "Knowledge_Base", tool_name: "query_knowledge_base", status: "pending" },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);

    expect(screen.getByText("Financial_Research")).toBeInTheDocument();
    expect(screen.getByText("get_stock_quote")).toBeInTheDocument();
    expect(screen.getByText("Knowledge_Base")).toBeInTheDocument();
    expect(screen.getByText("query_knowledge_base")).toBeInTheDocument();
  });

  it("shows succeeded status badge", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "server1", tool_name: "tool1", status: "succeeded" },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.getByLabelText("Succeeded")).toBeInTheDocument();
  });

  it("shows failed status badge", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "server1", tool_name: "tool1", status: "failed" },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.getByLabelText("Failed")).toBeInTheDocument();
  });

  it("shows pending status badge with animation", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "server1", tool_name: "tool1", status: "pending" },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.getByLabelText("Pending")).toBeInTheDocument();
  });

  it("displays duration for completed invocations", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "server1", tool_name: "tool1", status: "succeeded", duration_ms: 150 },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.getByText("150ms")).toBeInTheDocument();
  });

  it("does not display duration for pending invocations", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "server1", tool_name: "tool1", status: "pending", duration_ms: 100 },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.queryByText("100ms")).not.toBeInTheDocument();
  });

  it("displays error message for failed invocations", () => {
    const invocations: ToolInvocation[] = [
      {
        mcp_server: "Financial_Research",
        tool_name: "get_stock_quote",
        status: "failed",
        error_message: "INVALID_TICKER: Symbol XYZ not found",
      },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(
      screen.getByText("Error: INVALID_TICKER: Symbol XYZ not found")
    ).toBeInTheDocument();
  });

  it("shows total call count in header", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "s1", tool_name: "t1", status: "succeeded" },
      { mcp_server: "s2", tool_name: "t2", status: "succeeded" },
      { mcp_server: "s3", tool_name: "t3", status: "failed" },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.getByText("3 calls")).toBeInTheDocument();
    expect(screen.getByText("(1 failed)")).toBeInTheDocument();
  });

  it("shows singular 'call' for single invocation", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "s1", tool_name: "t1", status: "succeeded" },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.getByText("1 call")).toBeInTheDocument();
  });

  it("has accessible list structure", () => {
    const invocations: ToolInvocation[] = [
      { mcp_server: "s1", tool_name: "t1", status: "succeeded" },
      { mcp_server: "s2", tool_name: "t2", status: "pending" },
    ];

    render(<ToolInvocationPanel invocations={invocations} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
