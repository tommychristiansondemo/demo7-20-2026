import { useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import { useNavigate } from "react-router-dom";
import { ChatInterface } from "@/components/ChatInterface";

export function ChatPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [conversationId, setConversationId] = useState<string | undefined>();

  const handleSignOut = async () => {
    await signOut();
    navigate("/signin");
  };

  const handleConversationCreated = (id: string) => {
    setConversationId(id);
  };

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

      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-8">
        <div className="bg-white rounded-lg shadow h-full min-h-[60vh] flex flex-col">
          <ChatInterface
            conversationId={conversationId}
            onConversationCreated={handleConversationCreated}
          />
        </div>
      </main>
    </div>
  );
}
