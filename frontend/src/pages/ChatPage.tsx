import { useState, useCallback } from "react";
import { useAuth } from "@/auth/AuthContext";
import { useNavigate } from "react-router-dom";
import { ChatInterface } from "@/components/ChatInterface";
import { ConversationSidebar } from "@/components/ConversationSidebar";

export function ChatPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [chatKey, setChatKey] = useState(0);

  const handleSignOut = async () => {
    await signOut();
    navigate("/signin");
  };

  const handleConversationCreated = (id: string) => {
    setConversationId(id);
  };

  const handleSelectConversation = useCallback((id: string) => {
    setConversationId(id);
    // Increment key to force ChatInterface to remount and load new conversation
    setChatKey((prev) => prev + 1);
  }, []);

  const handleNewConversation = useCallback((id: string) => {
    setConversationId(id);
    // Increment key to force ChatInterface to remount with fresh state
    setChatKey((prev) => prev + 1);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-semibold text-gray-900">
            Agent Chat
          </h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-600">
              {user?.email}
            </span>
            <button
              onClick={handleSignOut}
              className="text-sm text-blue-600 hover:text-blue-500"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <ConversationSidebar
          activeConversationId={conversationId}
          onSelectConversation={handleSelectConversation}
          onNewConversation={handleNewConversation}
        />
        <div className="flex-1 flex flex-col p-4">
          <div className="bg-white rounded-lg shadow flex-1 flex flex-col min-h-0">
            <ChatInterface
              key={chatKey}
              conversationId={conversationId}
              onConversationCreated={handleConversationCreated}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
