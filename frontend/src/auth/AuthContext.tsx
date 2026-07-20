import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import {
  signIn as amplifySignIn,
  signUp as amplifySignUp,
  signOut as amplifySignOut,
  confirmSignUp as amplifyConfirmSignUp,
  getCurrentUser,
  fetchAuthSession,
} from "aws-amplify/auth";

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: { email: string; displayName?: string } | null;
  sessionToken: string | null;
}

export interface AuthActions {
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (
    email: string,
    password: string,
    displayName: string
  ) => Promise<void>;
  confirmSignUp: (email: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

interface AuthContextValue extends AuthState, AuthActions {}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    sessionToken: null,
  });

  const refreshSession = useCallback(async () => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString() ?? null;

      if (token) {
        const currentUser = await getCurrentUser();
        setState({
          isAuthenticated: true,
          isLoading: false,
          user: {
            email: currentUser.signInDetails?.loginId ?? "",
            displayName: currentUser.username,
          },
          sessionToken: token,
        });
      } else {
        setState({
          isAuthenticated: false,
          isLoading: false,
          user: null,
          sessionToken: null,
        });
      }
    } catch {
      setState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        sessionToken: null,
      });
    }
  }, []);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  // Check token expiration periodically (every 60 seconds)
  useEffect(() => {
    if (!state.isAuthenticated) return;

    const interval = setInterval(() => {
      refreshSession();
    }, 60_000);

    return () => clearInterval(interval);
  }, [state.isAuthenticated, refreshSession]);

  const signIn = async (email: string, password: string) => {
    await amplifySignIn({ username: email, password });
    await refreshSession();
  };

  const signUp = async (
    email: string,
    password: string,
    displayName: string
  ) => {
    await amplifySignUp({
      username: email,
      password,
      options: {
        userAttributes: {
          email,
          preferred_username: displayName,
        },
      },
    });
  };

  const confirmSignUp = async (email: string, code: string) => {
    await amplifyConfirmSignUp({ username: email, confirmationCode: code });
  };

  const signOut = async () => {
    await amplifySignOut();
    setState({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      sessionToken: null,
    });
  };

  return (
    <AuthContext.Provider
      value={{ ...state, signIn, signUp, confirmSignUp, signOut, refreshSession }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
