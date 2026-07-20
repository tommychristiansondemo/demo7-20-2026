import { useMemo } from "react";

export interface ToolInvocation {
  mcp_server: string;
  tool_name: string;
  status: "pending" | "succeeded" | "failed";
  duration_ms?: number;
  error_message?: string;
}

interface ToolInvocationPanelProps {
  invocations: ToolInvocation[];
}

export function ToolInvocationPanel({ invocations }: ToolInvocationPanelProps) {
  const summary = useMemo(() => {
    const succeeded = invocations.filter((i) => i.status === "succeeded").length;
    const failed = invocations.filter((i) => i.status === "failed").length;
    const pending = invocations.filter((i) => i.status === "pending").length;
    return { succeeded, failed, pending, total: invocations.length };
  }, [invocations]);

  if (invocations.length === 0) {
    return null;
  }

  return (
    <div
      className="border border-gray-200 rounded-lg bg-white shadow-sm"
      aria-label="Tool invocations"
    >
      <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700">Tool Invocations</h3>
        <span className="text-xs text-gray-500">
          {summary.total} call{summary.total !== 1 ? "s" : ""}
          {summary.failed > 0 && (
            <span className="text-red-500 ml-1">
              ({summary.failed} failed)
            </span>
          )}
        </span>
      </div>
      <ul className="divide-y divide-gray-100" role="list">
        {invocations.map((invocation, index) => (
          <ToolInvocationItem key={index} invocation={invocation} />
        ))}
      </ul>
    </div>
  );
}

function ToolInvocationItem({ invocation }: { invocation: ToolInvocation }) {
  return (
    <li className="px-3 py-2 flex items-center gap-2">
      <StatusBadge status={invocation.status} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1 text-sm">
          <span className="font-medium text-gray-800 truncate">
            {invocation.mcp_server}
          </span>
          <span className="text-gray-400">/</span>
          <span className="text-gray-600 truncate">{invocation.tool_name}</span>
        </div>
        {invocation.status === "failed" && invocation.error_message && (
          <p className="text-xs text-red-600 mt-0.5 truncate" role="alert">
            Error: {invocation.error_message}
          </p>
        )}
      </div>
      {invocation.duration_ms != null && invocation.status !== "pending" && (
        <span className="text-xs text-gray-400 whitespace-nowrap">
          {invocation.duration_ms}ms
        </span>
      )}
    </li>
  );
}

function StatusBadge({ status }: { status: ToolInvocation["status"] }) {
  switch (status) {
    case "succeeded":
      return (
        <span
          className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-green-100 text-green-600"
          aria-label="Succeeded"
        >
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    case "failed":
      return (
        <span
          className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-100 text-red-600"
          aria-label="Failed"
        >
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      );
    case "pending":
      return (
        <span
          className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-yellow-100 text-yellow-600 animate-pulse"
          aria-label="Pending"
        >
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <circle cx="10" cy="10" r="4" />
          </svg>
        </span>
      );
  }
}
