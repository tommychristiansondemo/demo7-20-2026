import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";

interface FieldErrors {
  email?: string;
  password?: string;
  displayName?: string;
}

const PASSWORD_REQUIREMENTS = [
  { label: "At least 8 characters", test: (p: string) => p.length >= 8 },
  { label: "At least one uppercase letter", test: (p: string) => /[A-Z]/.test(p) },
  { label: "At least one lowercase letter", test: (p: string) => /[a-z]/.test(p) },
  { label: "At least one number", test: (p: string) => /\d/.test(p) },
  { label: "At least one special character", test: (p: string) => /[^A-Za-z0-9]/.test(p) },
];

export function RegisterPage() {
  const { signUp } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validateEmail = (value: string): string | undefined => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!value) {
      return "Email is required.";
    }
    if (!emailRegex.test(value)) {
      return "Please enter a valid email address.";
    }
    return undefined;
  };

  const validateDisplayName = (value: string): string | undefined => {
    if (!value) {
      return "Display name is required.";
    }
    if (value.length < 2 || value.length > 50) {
      return "Display name must be between 2 and 50 characters.";
    }
    return undefined;
  };

  const validatePassword = (value: string): string | undefined => {
    if (!value) {
      return "Password is required.";
    }
    const failedRequirements = PASSWORD_REQUIREMENTS.filter((r) => !r.test(value));
    if (failedRequirements.length > 0) {
      return `Password must have: ${failedRequirements.map((r) => r.label.toLowerCase()).join(", ")}.`;
    }
    return undefined;
  };

  const validateAll = (): FieldErrors => {
    const errors: FieldErrors = {};
    errors.email = validateEmail(email);
    errors.displayName = validateDisplayName(displayName);
    errors.password = validatePassword(password);
    return errors;
  };

  const handleEmailBlur = () => {
    setFieldErrors((prev) => ({ ...prev, email: validateEmail(email) }));
  };

  const handleDisplayNameBlur = () => {
    setFieldErrors((prev) => ({ ...prev, displayName: validateDisplayName(displayName) }));
  };

  const handlePasswordBlur = () => {
    setFieldErrors((prev) => ({ ...prev, password: validatePassword(password) }));
  };

  const mapErrorMessage = (err: unknown): string => {
    const message = err instanceof Error ? err.message : String(err);
    const lower = message.toLowerCase();

    if (lower.includes("usernameexistsexception") || lower.includes("already exists") || lower.includes("already in use")) {
      return "An account with this email already exists.";
    }
    if (lower.includes("invalidpasswordexception") || lower.includes("password") && lower.includes("policy")) {
      return "Password does not meet requirements. Please review the password policy.";
    }
    if (lower.includes("invalidparameterexception")) {
      if (lower.includes("email")) {
        return "The email address format is invalid.";
      }
      if (lower.includes("preferred_username") || lower.includes("display")) {
        return "Display name must be between 2 and 50 characters.";
      }
      return "One or more fields are invalid. Please review your input.";
    }

    return message || "Registration failed. Please try again.";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const errors = validateAll();
    setFieldErrors(errors);

    const hasErrors = Object.values(errors).some((e) => e !== undefined);
    if (hasErrors) {
      return;
    }

    setIsSubmitting(true);
    try {
      await signUp(email, password, displayName);
      navigate("/verify", { state: { email } });
    } catch (err: unknown) {
      setFormError(mapErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-900">Create Account</h2>
          <p className="mt-2 text-gray-600">
            Register for the Bedrock AgentCore Demo
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit} noValidate>
          {formError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded" role="alert">
              {formError}
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
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (fieldErrors.email) {
                    setFieldErrors((prev) => ({ ...prev, email: undefined }));
                  }
                }}
                onBlur={handleEmailBlur}
                aria-invalid={!!fieldErrors.email}
                aria-describedby={fieldErrors.email ? "email-error" : undefined}
                className={`mt-1 block w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 ${
                  fieldErrors.email ? "border-red-500" : "border-gray-300"
                }`}
              />
              {fieldErrors.email && (
                <p id="email-error" className="mt-1 text-sm text-red-600" role="alert">
                  {fieldErrors.email}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="displayName" className="block text-sm font-medium text-gray-700">
                Display name
              </label>
              <input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => {
                  setDisplayName(e.target.value);
                  if (fieldErrors.displayName) {
                    setFieldErrors((prev) => ({ ...prev, displayName: undefined }));
                  }
                }}
                onBlur={handleDisplayNameBlur}
                aria-invalid={!!fieldErrors.displayName}
                aria-describedby={fieldErrors.displayName ? "displayName-error" : undefined}
                className={`mt-1 block w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 ${
                  fieldErrors.displayName ? "border-red-500" : "border-gray-300"
                }`}
              />
              {fieldErrors.displayName && (
                <p id="displayName-error" className="mt-1 text-sm text-red-600" role="alert">
                  {fieldErrors.displayName}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-500">Between 2 and 50 characters</p>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (fieldErrors.password) {
                    setFieldErrors((prev) => ({ ...prev, password: undefined }));
                  }
                }}
                onBlur={handlePasswordBlur}
                aria-invalid={!!fieldErrors.password}
                aria-describedby="password-requirements"
                className={`mt-1 block w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 ${
                  fieldErrors.password ? "border-red-500" : "border-gray-300"
                }`}
              />
              {fieldErrors.password && (
                <p className="mt-1 text-sm text-red-600" role="alert">
                  {fieldErrors.password}
                </p>
              )}
              <div id="password-requirements" className="mt-2 space-y-1">
                <p className="text-xs font-medium text-gray-600">Password requirements:</p>
                <ul className="text-xs space-y-0.5">
                  {PASSWORD_REQUIREMENTS.map((req) => {
                    const met = password.length > 0 && req.test(password);
                    return (
                      <li
                        key={req.label}
                        className={`flex items-center gap-1 ${
                          password.length === 0
                            ? "text-gray-500"
                            : met
                            ? "text-green-600"
                            : "text-red-500"
                        }`}
                      >
                        <span>{met ? "✓" : "○"}</span>
                        <span>{req.label}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            {isSubmitting ? "Creating account..." : "Register"}
          </button>

          <p className="text-center text-sm text-gray-600">
            Already have an account?{" "}
            <Link to="/signin" className="text-blue-600 hover:text-blue-500">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
