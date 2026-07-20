import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { configureApiClient } from "@/api/client";

/**
 * Connects the centralized API client to the auth context and router.
 * Must be rendered inside both AuthProvider and BrowserRouter.
 */
export function ApiClientProvider({ children }: { children: ReactNode }) {
  const { sessionToken, signOut } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    configureApiClient({
      baseUrl: "/api",
      getSessionToken: () => sessionToken,
      onUnauthorized: () => {
        signOut().catch(() => {});
        navigate("/signin", { replace: true });
      },
    });
  }, [sessionToken, signOut, navigate]);

  return <>{children}</>;
}
