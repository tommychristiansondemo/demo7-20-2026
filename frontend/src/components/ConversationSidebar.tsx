import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/auth/AuthContext";
import { api, ApiRequestError, NetworkError } from "@/api/client";

export interface Conversation {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface ConversationSidebarProps {
  activeConversationId?: string;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: (conversationId: string) => void;
}

export function ConversationSidebar({
  activeConversationId,
  onSelectConversation,
  onNewConversation,
}: ConversationSidebarProps) {
  const { sessionToken } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConversations = useCallback(async () => {
    if (!sessionToken) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await api.get<Conversation[] | { conversations: Conversation[] }>(
        "/chat/conversations"
      );
      const convos: Conversation[] = Array.isArray(data)
        ? data
        : (data as { conversations: Conversation[] }).conversations ?? [];

      // Order by most recent activity, cap at 50
      const sorted = convos
        .sort(
          (a, b) =>
            new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        )
        .slice(0, 50);

      setConversations(sorted);
    } catch (err: unknown) {
      if (err instanceof ApiRequestError && err.status === 401) {
        // 401 is handled globally by the client (redirect to /signin)
        return;
      }
      const message =
        err instanceof ApiRequestError || err instanceof NetworkError
          ? err.message
          : "Failed to load conversations";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [sessionToken]);

  // Load conversations on mount and when token changes
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const handleNewConversation = async () => {
    if (!sessionToken || isCreating) return;

    setIsCreating(true);
    setError(null);

    try {
      const data = await api.post<{
        conversation_id: string;
        title?: string;
        created_at?: string;
        updated_at?: string;
      }>("/chat/conversations", {});

      const newConvo: Conversation = {
        conversation_id: data.conversation_id,
        title: data.title || "New Conversation",
        created_at: data.created_at || new Date().toISOString(),
        updated_at: data.updated_at || new Date().toISOString(),
      };

      // Prepend to the list preserving existing conversations
      setConversations((prev) => [newConvo, ...prev].slice(0, 50));
      onNewConversation(newConvo.conversation_id);
    } catch (err: unknown) {
      if (err instanceof ApiRequestError && err.status === 401) {
        return;
      }
      const message =
        err instanceof ApiRequestError || err instanceof NetworkError
          ? err.message
          : "Failed to create conversation";
      setError(message);
    } finally {
      setIsCreating(false);
    }
  };

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <aside
      className="w-64 bg-white border-r border-gray-200 flex flex-col h-full"
      aria-label="Conversation sidebar"
    >
      {/* New Conversation Button */}
      <div className="p-3 border-b border-gray-200">
        <button
          onClick={handleNewConversation}
          disabled={isCreating}
          className="w-full px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          aria-label="New Conversation"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          {isCreating ? "Creating..." : "New Conversation"}
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && conversations.length === 0 && (
          <div className="p-4 text-center text-sm text-gray-500">
            Loading conversations...
          </div>
        )}

        {error && (
          <div className="p-3 m-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md">
            {error}
            <button
              onClick={fetchConversations}
              className="ml-2 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !error && conversations.length === 0 && (
          <div className="p-4 text-center text-sm text-gray-500">
            No conversations yet. Start a new one!
          </div>
        )}

        <ul className="divide-y divide-gray-100" role="list">
          {conversations.map((convo) => (
            <li key={convo.conversation_id}>
              <button
                onClick={() => onSelectConversation(convo.conversation_id)}
                className={`w-full text-left px-3 py-3 hover:bg-gray-50 focus:outline-none focus:bg-gray-100 transition-colors ${
                  activeConversationId === convo.conversation_id
                    ? "bg-blue-50 border-l-2 border-blue-600"
                    : ""
                }`}
                aria-current={
                  activeConversationId === convo.conversation_id
                    ? "true"
                    : undefined
                }
              >
                <p className="text-sm font-medium text-gray-900 truncate">
                  {convo.title || "Untitled"}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {formatTimestamp(convo.updated_at)}
                </p>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
