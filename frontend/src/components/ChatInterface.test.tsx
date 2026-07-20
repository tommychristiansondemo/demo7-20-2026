import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ChatInterface } from "./ChatInterface";
import { configureApiClient } from "@/api/client";

// Mock useAuth
vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    sessionToken: "mock-token-123",
  }),
}));

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("ChatInterface", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch.mockReset();
    configureApiClient({
      baseUrl: "/api",
      getSessionToken: () => "mock-token-123",
      onUnauthorized: () => {},
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders empty state message", () => {
    render(<ChatInterface />);
    expect(
      screen.getByText("Start a conversation with the AI agent.")
    ).toBeInTheDocument();
  });

  it("displays validation error for empty message", async () => {
    vi.useRealTimers();
    render(<ChatInterface />);
    const sendButton = screen.getByRole("button", { name: /send message/i });
    fireEvent.click(sendButton);
    expect(
      await screen.findByText(/message cannot be empty/i)
    ).toBeInTheDocument();
  });

  it("displays validation error for whitespace-only message", async () => {
    vi.useRealTimers();
    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "   " } });
    const sendButton = screen.getByRole("button", { name: /send message/i });
    fireEvent.click(sendButton);
    expect(
      await screen.findByText(/message cannot be empty/i)
    ).toBeInTheDocument();
  });

  it("displays validation error for message exceeding 2000 chars", async () => {
    vi.useRealTimers();
    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    const longMessage = "a".repeat(2001);
    fireEvent.change(input, { target: { value: longMessage } });
    const sendButton = screen.getByRole("button", { name: /send message/i });
    fireEvent.click(sendButton);
    expect(
      await screen.findByText(/exceeds the maximum length/i)
    ).toBeInTheDocument();
  });

  it("shows character counter", () => {
    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "Hello" } });
    expect(screen.getByText("5/2000")).toBeInTheDocument();
  });

  it("sends message and displays user message bubble", async () => {
    vi.useRealTimers();
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        response: "Hello from the agent!",
        message_id: "msg-1",
      }),
    });

    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "Hello" } });
    const sendButton = screen.getByRole("button", { name: /send message/i });
    fireEvent.click(sendButton);

    // User message should appear
    expect(await screen.findByText("Hello")).toBeInTheDocument();
    // Agent response should appear
    expect(
      await screen.findByText("Hello from the agent!")
    ).toBeInTheDocument();
  });

  it("sends correct API request with auth token", async () => {
    vi.useRealTimers();
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ response: "OK" }),
    });

    render(<ChatInterface conversationId="conv-123" />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "test message" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/chat/message",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Content-Type": "application/json",
            Authorization: "Bearer mock-token-123",
          }),
          body: JSON.stringify({
            message: "test message",
            conversation_id: "conv-123",
          }),
        })
      );
    });
  });

  it("retains message in input on send failure", async () => {
    vi.useRealTimers();
    mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "My important message" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => {
      expect(input.value).toBe("My important message");
    });
    expect(
      await screen.findByText(/network error/i)
    ).toBeInTheDocument();
  });

  it("displays timeout message after 30 seconds", async () => {
    // Mock fetch that respects abort signal
    mockFetch.mockImplementation(
      (_url: string, opts?: { signal?: AbortSignal }) =>
        new Promise((_, reject) => {
          if (opts?.signal) {
            opts.signal.addEventListener("abort", () => {
              reject(new DOMException("The operation was aborted.", "AbortError"));
            });
          }
        })
    );

    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    // Advance by 30 seconds to trigger the timeout
    await vi.advanceTimersByTimeAsync(30000);

    expect(
      screen.getByText(/timed out/i)
    ).toBeInTheDocument();
  });

  it("displays loading indicator while processing", async () => {
    mockFetch.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    // Wait a tick for state update
    await vi.advanceTimersByTimeAsync(50);

    expect(
      screen.getByText("Agent is thinking...")
    ).toBeInTheDocument();
  });

  it("disables input and button while loading", async () => {
    mockFetch.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    await vi.advanceTimersByTimeAsync(50);

    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("clears validation error when user types", async () => {
    vi.useRealTimers();
    render(<ChatInterface />);
    const input = screen.getByLabelText(/chat message input/i);
    const sendButton = screen.getByRole("button", { name: /send message/i });

    // Trigger validation error
    fireEvent.click(sendButton);
    expect(
      await screen.findByText(/message cannot be empty/i)
    ).toBeInTheDocument();

    // Type to clear error
    fireEvent.change(input, { target: { value: "x" } });
    expect(
      screen.queryByText(/message cannot be empty/i)
    ).not.toBeInTheDocument();
  });

  it("calls onConversationCreated when new conversation is created", async () => {
    vi.useRealTimers();
    const onCreated = vi.fn();
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        response: "Hi!",
        conversation_id: "new-conv-456",
      }),
    });

    render(<ChatInterface onConversationCreated={onCreated} />);
    const input = screen.getByLabelText(/chat message input/i);
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith("new-conv-456");
    });
  });
});
