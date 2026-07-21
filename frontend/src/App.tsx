import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/auth";
import { ApiClientProvider } from "@/api/ApiClientProvider";
import { RouteGuard } from "@/auth/RouteGuard";
import {
  RegisterPage,
  SignInPage,
  VerifyPage,
  DashboardPage,
  ChatPage,
  ObservePage,
} from "@/pages";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ApiClientProvider>
          <Routes>
            {/* Public routes */}
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/signin" element={<SignInPage />} />
            <Route path="/verify" element={<VerifyPage />} />

            {/* Protected routes */}
            <Route
              path="/dashboard"
              element={
                <RouteGuard>
                  <DashboardPage />
                </RouteGuard>
              }
            />
            <Route
              path="/chat"
              element={
                <RouteGuard>
                  <ChatPage />
                </RouteGuard>
              }
            />
            <Route
              path="/observe"
              element={
                <RouteGuard>
                  <ObservePage />
                </RouteGuard>
              }
            />

            {/* Default redirect */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </ApiClientProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
