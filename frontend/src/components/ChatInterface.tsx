import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "@/auth/AuthContext";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  tool_invocations?: ToolInvocation[];
  error?: boolean;
}

interface ToolInvocation {
  mcp_server: string;
  tool_name: string;
  status: "pending" | "succeeded" | "failed";
  duration_ms?: number;
}

interface ChatInterfaceProps {
  conversationId?: string;
  onConversationCreated?: (id: string) => void;
}

const MAX_MESSAGE_LENGTH = 2000;
const TIMEOUT_MS = 30000;

export function ChatInterface({ conversationId, onConversationCreated }: ChatInterfaceProps) {
  const { sessionToken } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const validateMessage = (message: string): string | null => {
    const trimmed = message.trim();
    if (trimmed.length === 0) {
      return "Message cannot be empty. Please enter a message between 1 and 2000 characters.";
    }
    if (trimmed.length > MAX_MESSAGE_LENGTH) {
      return `Message exceeds the maximum length of ${MAX_MESSAGE_LENGTH} characters (currently ${trimmed.length}).`;
    }
    return null;
  };

  const handleSend = async () => {
    const trimmed = inputValue.trim();
    const error = validateMessage(inputValue);
    if (error) {
      setValidationError(error);
      return;
    }

    setValidationError(null);
    setSendError(null);
    setIsLoading(true);

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    // Keep the input value in case sending fails
    const previousInput = inputValue;
    setInputValue("");

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    // Set up 30-second timeout
    timeoutRef.current = setTimeout(() => {
      abortController.abort();
      setIsLoading(false);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Request timed out. The agent could not complete processing within 30 seconds. Please try again or rephrase your question.",
          timestamp: new Date().toISOString(),
          error: true,
        },
      ]);
    }, TIMEOUT_MS);

    try {
      const response = await fetch("/api/chat/message", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${sessionToken}`,
        },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: conversationId,
        }),
        signal: abortController.signal,
      });

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }

      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      const data = await response.json();

      if (data.conversation_id && !conversationId && onConversationCreated) {
        onConversationCreated(data.conversation_id);
      }

      const assistantMessage: Message = {
        id: data.message_id || crypto.randomUUID(),
        role: "assistant",
        content: data.response || data.content || "",
        timestamp: new Date().toISOString(),
        tool_invocations: data.tool_invocations,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: unknown) {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }

      // If aborted by timeout, the timeout handler already set the error message
      if (err instanceof Error && err.name === "AbortError") {
        // Timeout already handled - restore input so user can retry
        setInputValue(previousInput);
        setIsLoading(false);
        return;
      }

      // Persist error — retain unsent message in input
      setInputValue(previousInput);
      setSendError("Failed to send message. Please try again.");
      // Remove the user message we optimistically added
      setMessages((prev) => prev.filter((m) => m.id !== userMessage.id));
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading) {
        handleSend();
      }
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    if (validationError) {
      setValidationError(null);
    }
    if (sendError) {
      setSendError(null);
    }
  };

  const charCount = inputValue.trim().length;
  const isOverLimit = charCount > MAX_MESSAGE_LENGTH;

  return (
    <div className="flex flex-col h-full">
      {/* Message List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-gray-500 text-center mt-8">
            Start a conversation with the AI agent.
          </p>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && <LoadingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t p-4 bg-white">
        {validationError && (
          <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2" role="alert">
            {validationError}
          </div>
        )}
        {sendError && (
          <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2" role="alert">
            {sendError}
          </div>
        )}
        <div className="flex gap-2 items-end">
          <div className="flex-1 relative">
            <textarea
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              disabled={isLoading}
              rows={1}
              className={`w-full px-3 py-2 border rounded-md shadow-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:bg-gray-50 ${
                isOverLimit ? "border-red-300" : "border-gray-300"
              }`}
              aria-label="Chat message input"
              aria-invalid={!!validationError}
              aria-describedby={validationError ? "validation-error" : undefined}
            />
            <span
              className={`absolute bottom-1 right-2 text-xs ${
                isOverLimit ? "text-red-500 font-medium" : "text-gray-400"
              }`}
            >
              {charCount}/{MAX_MESSAGE_LENGTH}
            </span>
          </div>
          <button
            onClick={handleSend}
            disabled={isLoading}
            className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Send message"
          >
            {isLoading ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? "bg-blue-600 text-white"
            : message.error
            ? "bg-red-50 text-red-800 border border-red-200"
            : "bg-gray-100 text-gray-900"
        }`}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {message.tool_invocations && message.tool_invocations.length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-200/50">
            {message.tool_invocations.map((tool, idx) => (
              <div
                key={idx}
                className="text-xs flex items-center gap-1 mt-1 opacity-80"
              >
                <StatusIcon status={tool.status} />
                <span>
                  {tool.mcp_server}/{tool.tool_name}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "succeeded":
      return <span className="text-green-500">✓</span>;
    case "failed":
      return <span className="text-red-500">✗</span>;
    case "pending":
      return <span className="animate-pulse">⋯</span>;
    default:
      return null;
  }
}

function LoadingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-gray-100 rounded-lg px-4 py-3 flex items-center gap-2">
        <div className="flex space-x-1">
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
        <span className="text-sm text-gray-500">Agent is thinking...</span>
      </div>
    </div>
  );
}
