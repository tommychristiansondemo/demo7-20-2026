import { useAuth } from "@/auth/AuthContext";
import { useNavigate } from "react-router-dom";

export function DashboardPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const handleSignOut = async () => {
    await signOut();
    navigate("/signin");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-semibold text-gray-900">
            Bedrock AgentCore Demo
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

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Welcome</h2>
          <p className="text-gray-600 mb-4">
            You're signed in to the Bedrock AgentCore Demo. Use the chat to
            interact with the AI agent.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => navigate("/chat")}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
            >
              Open Chat
            </button>
            <button
              onClick={() => navigate("/observe")}
              className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
            >
              Observability Dashboard
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
