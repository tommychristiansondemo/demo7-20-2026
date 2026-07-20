import { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { resendSignUpCode } from "aws-amplify/auth";

export function VerifyPage() {
  const { confirmSignUp } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const emailFromState = (location.state as { email?: string })?.email || "";
  const [email, setEmail] = useState(emailFromState);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);

  const mapVerifyError = (err: unknown): string => {
    const message = err instanceof Error ? err.message : String(err);
    const lower = message.toLowerCase();

    if (lower.includes("codemismatchexception") || lower.includes("invalid") && lower.includes("code")) {
      return "The verification code is invalid. Please check the code and try again.";
    }
    if (lower.includes("expiredcodeexception") || lower.includes("expired")) {
      return "The verification code has expired. Please request a new code.";
    }
    if (lower.includes("limitexceededexception") || lower.includes("limit")) {
      return "Too many attempts. Please wait before trying again.";
    }

    return message || "Verification failed. The code may be invalid or expired.";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!email.trim()) {
      setError("Email address is required.");
      return;
    }

    if (!code.trim()) {
      setError("Verification code is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      await confirmSignUp(email, code);
      navigate("/signin", { state: { verified: true } });
    } catch (err: unknown) {
      setError(mapVerifyError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendCode = async () => {
    setError(null);
    setSuccess(null);

    if (!email.trim()) {
      setError("Please enter your email address to resend the code.");
      return;
    }

    setIsResending(true);
    try {
      await resendSignUpCode({ username: email });
      setSuccess("A new verification code has been sent to your email.");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      const lower = message.toLowerCase();

      if (lower.includes("limitexceededexception") || lower.includes("limit")) {
        setError("Too many resend attempts. Please wait before trying again.");
      } else {
        setError("Failed to resend verification code. Please try again.");
      }
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-900">Verify Email</h2>
          <p className="mt-2 text-gray-600">
            Enter the verification code sent to your email
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded" role="alert">
              {error}
            </div>
          )}

          {success && (
            <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded" role="status">
              {success}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label htmlFor="code" className="block text-sm font-medium text-gray-700">
                Verification code
              </label>
              <input
                id="code"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Enter 6-digit code"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            {isSubmitting ? "Verifying..." : "Verify"}
          </button>

          <div className="text-center space-y-2">
            <button
              type="button"
              onClick={handleResendCode}
              disabled={isResending}
              className="text-sm text-blue-600 hover:text-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isResending ? "Sending..." : "Didn't receive a code? Resend"}
            </button>
            <p className="text-sm text-gray-600">
              <Link to="/signin" className="text-blue-600 hover:text-blue-500">
                Back to sign in
              </Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
