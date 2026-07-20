import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConversationSidebar } from "./ConversationSidebar";
import { configureApiClient } from "@/api/client";

// Mock the useAuth hook
vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    sessionToken: "test-token",
  }),
}));

// Setup fetch mock
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("ConversationSidebar", () => {
  const defaultProps = {
    onSelectConversation: vi.fn(),
    onNewConversation: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    configureApiClient({
      baseUrl: "/api",
      getSessionToken: () => "test-token",
      onUnauthorized: () => {},
    });
  });

  it("renders empty state when no conversations exist", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [],
    });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText("No conversations yet. Start a new one!")
      ).toBeInTheDocument();
    });
  });

  it("fetches and displays conversations ordered by most recent", async () => {
    const conversations = [
      {
        conversation_id: "conv-1",
        title: "First Conversation",
        created_at: "2024-01-01T10:00:00Z",
        updated_at: "2024-01-01T10:00:00Z",
      },
      {
        conversation_id: "conv-2",
        title: "Second Conversation",
        created_at: "2024-01-02T10:00:00Z",
        updated_at: "2024-01-02T12:00:00Z",
      },
      {
        conversation_id: "conv-3",
        title: "Third Conversation",
        created_at: "2024-01-03T10:00:00Z",
        updated_at: "2024-01-03T15:00:00Z",
      },
    ];

    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => conversations,
    });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Third Conversation")).toBeInTheDocument();
      expect(screen.getByText("Second Conversation")).toBeInTheDocument();
      expect(screen.getByText("First Conversation")).toBeInTheDocument();
    });

    // Verify the order: Third (most recent) should come first
    const items = screen.getAllByRole("button", { name: /Conversation/i });
    // Filter out the "New Conversation" button
    const conversationButtons = items.filter(
      (btn) => !btn.textContent?.includes("New")
    );
    expect(conversationButtons[0]).toHaveTextContent("Third Conversation");
    expect(conversationButtons[1]).toHaveTextContent("Second Conversation");
    expect(conversationButtons[2]).toHaveTextContent("First Conversation");
  });

  it("calls onSelectConversation when a conversation is clicked", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [
        {
          conversation_id: "conv-1",
          title: "Test Conversation",
          created_at: "2024-01-01T10:00:00Z",
          updated_at: "2024-01-01T10:00:00Z",
        },
      ],
    });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Test Conversation")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText("Test Conversation"));
    expect(defaultProps.onSelectConversation).toHaveBeenCalledWith("conv-1");
  });

  it("creates a new conversation on button click", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          conversation_id: "new-conv-123",
          title: "New Conversation",
          created_at: "2024-01-04T10:00:00Z",
          updated_at: "2024-01-04T10:00:00Z",
        }),
      });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText("No conversations yet. Start a new one!")
      ).toBeInTheDocument();
    });

    await userEvent.click(
      screen.getByRole("button", { name: "New Conversation" })
    );

    await waitFor(() => {
      expect(defaultProps.onNewConversation).toHaveBeenCalledWith(
        "new-conv-123"
      );
    });

    // The POST request should have been made with auth header
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/chat/conversations",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer test-token",
        }),
      })
    );
  });

  it("highlights the active conversation", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [
        {
          conversation_id: "conv-active",
          title: "Active Conversation",
          created_at: "2024-01-01T10:00:00Z",
          updated_at: "2024-01-01T10:00:00Z",
        },
      ],
    });

    render(
      <ConversationSidebar
        {...defaultProps}
        activeConversationId="conv-active"
      />
    );

    await waitFor(() => {
      const activeButton = screen.getByText("Active Conversation").closest("button");
      expect(activeButton).toHaveAttribute("aria-current", "true");
    });
  });

  it("displays error state and allows retry", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ message: "Failed to load conversations" }),
    });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText(/Failed to load conversations/)
      ).toBeInTheDocument();
    });

    // Click retry
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [],
    });

    await userEvent.click(screen.getByText("Retry"));

    await waitFor(() => {
      expect(
        screen.getByText("No conversations yet. Start a new one!")
      ).toBeInTheDocument();
    });
  });

  it("sends authorization header when fetching conversations", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [],
    });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/chat/conversations",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer test-token",
          }),
        })
      );
    });
  });

  it("caps conversation list at 50 items", async () => {
    const manyConversations = Array.from({ length: 60 }, (_, i) => ({
      conversation_id: `conv-${i}`,
      title: `Conversation ${i}`,
      created_at: `2024-01-${String(i + 1).padStart(2, "0")}T10:00:00Z`,
      updated_at: `2024-01-${String(i + 1).padStart(2, "0")}T10:00:00Z`,
    }));

    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => manyConversations,
    });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      const listItems = screen.getAllByRole("listitem");
      expect(listItems.length).toBeLessThanOrEqual(50);
    });
  });

  it("preserves previous conversations in sidebar when new one is created", async () => {
    const existingConversations = [
      {
        conversation_id: "conv-1",
        title: "Existing Conversation",
        created_at: "2024-01-01T10:00:00Z",
        updated_at: "2024-01-01T10:00:00Z",
      },
    ];

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => existingConversations,
      })
      .mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          conversation_id: "new-conv",
          title: "My Fresh Chat",
          created_at: "2024-01-05T10:00:00Z",
          updated_at: "2024-01-05T10:00:00Z",
        }),
      });

    render(<ConversationSidebar {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Existing Conversation")).toBeInTheDocument();
    });

    await userEvent.click(
      screen.getByRole("button", { name: "New Conversation" })
    );

    await waitFor(() => {
      // Both conversations should be present in the list
      expect(screen.getByText("My Fresh Chat")).toBeInTheDocument();
      expect(screen.getByText("Existing Conversation")).toBeInTheDocument();
    });

    // Verify the list has 2 items
    const listItems = screen.getAllByRole("listitem");
    expect(listItems).toHaveLength(2);
  });
});
