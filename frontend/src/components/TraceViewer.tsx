import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/auth/AuthContext";
import { api, ApiRequestError, NetworkError } from "@/api/client";

export interface TraceSpan {
  name: string;
  mcp_server: string | null;
  tool_name: string | null;
  duration_ms: number;
  status: "success" | "failure";
}

export interface TraceData {
  request_id: string;
  trace: {
    total_latency_ms: number;
    tool_call_count: number;
    prompt_tokens: number;
    completion_tokens: number;
    spans: TraceSpan[];
  };
  tool_invocations: Array<{
    mcp_server: string;
    tool_name: string;
    status: "pending" | "succeeded" | "failed";
    duration_ms?: number;
  }>;
}

interface TraceViewerProps {
  requestId: string;
  onError?: (error: string) => void;
}

const FETCH_TIMEOUT_MS = 3000;

export function TraceViewer({ requestId, onError }: TraceViewerProps) {
  const { sessionToken } = useAuth();
  const [traceData, setTraceData] = useState<TraceData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTrace = useCallback(async () => {
    if (!requestId || !sessionToken) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await api.get<TraceData>(`/chat/trace/${requestId}`, {
        timeout: FETCH_TIMEOUT_MS,
        maxRetries: 0, // No retries for trace - quick fail
      });
      setTraceData(data);
    } catch (err: unknown) {
      const message =
        err instanceof NetworkError && err.message.includes("timed out")
          ? "Trace data could not be loaded within 3 seconds."
          : err instanceof ApiRequestError
          ? err.message
          : err instanceof NetworkError
          ? err.message
          : "Failed to load trace data.";
      setError(message);
      onError?.(message);
    } finally {
      setIsLoading(false);
    }
  }, [requestId, sessionToken, onError]);

  useEffect(() => {
    fetchTrace();
  }, [fetchTrace]);

  if (isLoading) {
    return (
      <div className="border border-gray-200 rounded-lg bg-white p-4" aria-label="Trace viewer">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <LoadingSpinner />
          <span>Loading trace data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="border border-red-200 rounded-lg bg-red-50 p-4"
        aria-label="Trace viewer"
        role="alert"
      >
        <p className="text-sm text-red-700">{error}</p>
        <button
          onClick={fetchTrace}
          className="mt-2 text-xs text-red-600 underline hover:text-red-800"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!traceData) {
    return null;
  }

  const { trace } = traceData;

  return (
    <div
      className="border border-gray-200 rounded-lg bg-white shadow-sm"
      aria-label="Trace viewer"
    >
      {/* Summary header */}
      <div className="px-3 py-2 border-b border-gray-100">
        <h3 className="text-sm font-medium text-gray-700">Request Trace</h3>
        <div className="flex flex-wrap gap-3 mt-1 text-xs text-gray-500">
          <span>Latency: {trace.total_latency_ms}ms</span>
          <span>Tool calls: {trace.tool_call_count}</span>
          <span>Tokens: {trace.prompt_tokens + trace.completion_tokens}</span>
        </div>
      </div>

      {/* Span timeline */}
      <div className="px-3 py-2">
        {trace.spans.length === 0 ? (
          <p className="text-sm text-gray-500">No trace spans recorded.</p>
        ) : (
          <ol className="relative border-l border-gray-200 ml-2 space-y-2" role="list">
            {trace.spans.map((span, index) => (
              <TraceSpanItem
                key={index}
                span={span}
                totalLatency={trace.total_latency_ms}
              />
            ))}
          </ol>
        )}
      </div>

      {/* Token usage footer */}
      <div className="px-3 py-2 border-t border-gray-100 flex gap-4 text-xs text-gray-500">
        <span>Prompt: {trace.prompt_tokens} tokens</span>
        <span>Completion: {trace.completion_tokens} tokens</span>
      </div>
    </div>
  );
}

function TraceSpanItem({
  span,
  totalLatency,
}: {
  span: TraceSpan;
  totalLatency: number;
}) {
  const isToolCall = span.mcp_server != null && span.tool_name != null;
  const percentage =
    totalLatency > 0 ? Math.round((span.duration_ms / totalLatency) * 100) : 0;

  return (
    <li className="ml-4">
      <div
        className={`absolute -left-1.5 mt-1.5 w-3 h-3 rounded-full border-2 border-white ${
          span.status === "success" ? "bg-green-400" : "bg-red-400"
        }`}
      />
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">
            {span.name}
          </p>
          {isToolCall && (
            <p className="text-xs text-gray-500 truncate">
              {span.mcp_server}/{span.tool_name}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <SpanStatusBadge status={span.status} />
          <span className="text-xs text-gray-400 whitespace-nowrap">
            {span.duration_ms}ms
            {percentage > 0 && (
              <span className="ml-1 text-gray-300">({percentage}%)</span>
            )}
          </span>
        </div>
      </div>
      {/* Duration bar */}
      <div className="mt-1 h-1 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${
            span.status === "success" ? "bg-green-300" : "bg-red-300"
          }`}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    </li>
  );
}

function SpanStatusBadge({ status }: { status: "success" | "failure" }) {
  if (status === "success") {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 text-xs font-medium rounded bg-green-100 text-green-700">
        OK
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 text-xs font-medium rounded bg-red-100 text-red-700">
      FAIL
    </span>
  );
}

function LoadingSpinner() {
  return (
    <svg
      className="animate-spin h-4 w-4 text-gray-400"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}
