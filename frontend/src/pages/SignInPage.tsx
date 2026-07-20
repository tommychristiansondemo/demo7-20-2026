import { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";

type SignInError = "invalid_credentials" | "account_locked" | "service_unavailable";

function getErrorType(error: unknown): SignInError {
  if (error instanceof Error) {
    const name = (error as { name?: string }).name ?? "";
    const message = error.message ?? "";

    // Account locked after too many failed attempts
    if (
      name === "NotAuthorizedException" &&
      (message.toLowerCase().includes("exceeded") ||
        message.toLowerCase().includes("temporarily locked") ||
        message.toLowerCase().includes("attempt limit"))
    ) {
      return "account_locked";
    }

    // LimitExceededException also indicates lockout
    if (name === "LimitExceededException") {
      return "account_locked";
    }

    // Network or service errors indicate Cognito is unavailable
    if (
      name === "NetworkError" ||
      name === "ServiceUnavailableException" ||
      message.toLowerCase().includes("network") ||
      message.toLowerCase().includes("service unavailable") ||
      message.toLowerCase().includes("fetch failed")
    ) {
      return "service_unavailable";
    }
  }

  // Default to generic invalid credentials for any other auth failure
  return "invalid_credentials";
}

const ERROR_MESSAGES: Record<SignInError, string> = {
  invalid_credentials:
    "Sign-in failed. Please check your credentials and try again.",
  account_locked:
    "Your account has been temporarily locked due to too many failed sign-in attempts. Please try again in 15 minutes.",
  service_unavailable:
    "The authentication service is temporarily unavailable. Please try again in a few moments.",
};

export function SignInPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<SignInError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const from =
    (location.state as { from?: { pathname: string } })?.from?.pathname ||
    "/dashboard";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await signIn(email, password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      setError(getErrorType(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-900">Sign In</h2>
          <p className="mt-2 text-gray-600">Bedrock AgentCore Demo</p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div
              role="alert"
              className={`px-4 py-3 rounded border ${
                error === "account_locked"
                  ? "bg-yellow-50 border-yellow-200 text-yellow-800"
                  : error === "service_unavailable"
                    ? "bg-orange-50 border-orange-200 text-orange-800"
                    : "bg-red-50 border-red-200 text-red-700"
              }`}
            >
              {ERROR_MESSAGES[error]}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-700"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Signing in..." : "Sign In"}
          </button>

          <p className="text-center text-sm text-gray-600">
            Don't have an account?{" "}
            <Link to="/register" className="text-blue-600 hover:text-blue-500">
              Register
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
