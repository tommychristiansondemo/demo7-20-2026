import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { api } from "@/api/client";

interface TelemetryFeedItem {
  record_id: string;
  student_email: string;
  message_preview: string;
  total_latency_ms: number;
  tool_call_count: number;
  timestamp: string;
}

interface TelemetryFeedResponse {
  records: TelemetryFeedItem[];
  average_latency_ms: number;
}

interface ThinkingResponse {
  record_id: string;
  thinking_content: string;
  has_thinking: boolean;
}

export function ObservePage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const [records, setRecords] = useState<TelemetryFeedItem[]>([]);
  const [averageLatencyMs, setAverageLatencyMs] = useState(0);
  const [isLoadingFeed, setIsLoadingFeed] = useState(true);
  const [feedError, setFeedError] = useState<string | null>(null);

  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  const [thinkingContent, setThinkingContent] = useState<string | null>(null);
  const [isLoadingThinking, setIsLoadingThinking] = useState(false);
  const [thinkingError, setThinkingError] = useState<string | null>(null);

  const fetchFeed = useCallback(async () => {
    try {
      const data = await api.get<TelemetryFeedResponse>("/observe/feed");
      setRecords(data.records);
      setAverageLatencyMs(data.average_latency_ms);
      setFeedError(null);
    } catch {
      setFeedError("Unable to load telemetry");
    } finally {
      setIsLoadingFeed(false);
    }
  }, []);

  useEffect(() => {
    fetchFeed();
    const interval = setInterval(fetchFeed, 10000);
    return () => clearInterval(interval);
  }, [fetchFeed]);

  const handleRowClick = async (recordId: string) => {
    if (selectedRecordId === recordId) {
      setSelectedRecordId(null);
      setThinkingContent(null);
      return;
    }

    setSelectedRecordId(recordId);
    setIsLoadingThinking(true);
    setThinkingError(null);

    try {
      const data = await api.get<ThinkingResponse>(
        `/observe/thinking/${recordId}`
      );
      setThinkingContent(data.thinking_content);
    } catch {
      setThinkingError("Unable to load thinking content");
      setThinkingContent(null);
    } finally {
      setIsLoadingThinking(false);
    }
  };

  const handleSignOut = async () => {
    await signOut();
    navigate("/signin");
  };

  const formatTimestamp = (ts: string) => {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-semibold text-gray-900">
            Observability Dashboard
          </h1>
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/dashboard")}
              className="text-sm text-blue-600 hover:text-blue-500"
            >
              Dashboard
            </button>
            <span className="text-sm text-gray-600">{user?.email}</span>
            <button
              onClick={handleSignOut}
              className="text-sm text-blue-600 hover:text-blue-500"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        {/* Average Latency Card */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
            Average Latency
          </h2>
          <p className="mt-2 text-3xl font-bold text-gray-900">
            {averageLatencyMs.toFixed(1)} ms
          </p>
          <p className="text-sm text-gray-500 mt-1">
            Rolling average across last {records.length} request
            {records.length !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Feed Table */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-medium text-gray-900">
              Recent Inference Activity
            </h2>
          </div>

          {feedError && (
            <div className="px-6 py-4 text-red-600">
              {feedError}
              <button
                onClick={fetchFeed}
                className="ml-4 text-sm text-blue-600 hover:text-blue-500 underline"
              >
                Retry
              </button>
            </div>
          )}

          {isLoadingFeed && !feedError && (
            <div className="px-6 py-8 text-center text-gray-500">
              Loading...
            </div>
          )}

          {!isLoadingFeed && !feedError && records.length === 0 && (
            <div className="px-6 py-8 text-center text-gray-500">
              No inference activity yet
            </div>
          )}

          {!isLoadingFeed && !feedError && records.length > 0 && (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Student Email
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Message Preview
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Latency (ms)
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Tool Calls
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Timestamp
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {records.map((record) => (
                    <tr
                      key={record.record_id}
                      onClick={() => handleRowClick(record.record_id)}
                      className={`cursor-pointer hover:bg-blue-50 transition-colors ${
                        selectedRecordId === record.record_id
                          ? "bg-blue-50"
                          : ""
                      }`}
                    >
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {record.student_email}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-700 max-w-xs truncate">
                        {record.message_preview}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {record.total_latency_ms.toFixed(1)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {record.tool_call_count}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatTimestamp(record.timestamp)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Thinking Panel */}
        {selectedRecordId && (
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Reasoning Chain
            </h3>
            {isLoadingThinking && (
              <p className="text-gray-500">Loading thinking content...</p>
            )}
            {thinkingError && (
              <p className="text-red-600">{thinkingError}</p>
            )}
            {!isLoadingThinking && !thinkingError && (
              <div className="prose max-w-none">
                {thinkingContent ? (
                  <pre className="whitespace-pre-wrap text-sm text-gray-800 bg-gray-50 p-4 rounded-md overflow-auto max-h-96">
                    {thinkingContent}
                  </pre>
                ) : (
                  <p className="text-gray-500 italic">
                    No reasoning chain available
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
