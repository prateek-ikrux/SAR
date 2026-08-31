import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import { setUnauthorizedHandler } from "@/lib/api";
import { clearToken } from "@/lib/authToken";
import { meKey, useMe } from "@/hooks/useAuth";
import AppShell from "@/components/AppShell";
import SignInPage from "@/pages/SignInPage";
import SearchPage from "@/pages/SearchPage";
import UsersPage from "@/pages/UsersPage";

function FullPageSpinner() {
  return (
    <div className="flex min-h-svh items-center justify-center">
      <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-foreground" />
    </div>
  );
}

function RequireAuth({ children, adminOnly = false }) {
  const { data: user, isPending } = useMe();
  if (isPending) return <FullPageSpinner />;
  if (!user) return <Navigate to="/sign-in" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // One place decides what a 401 means. There is no refresh token, so the
  // session is simply over: drop the stored token and let RequireAuth route to
  // sign-in. The api interceptor clears it too, so this also covers a session
  // ended from anywhere that does not go through axios.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearToken();
      queryClient.setQueryData(meKey, null);
      navigate("/sign-in", { replace: true });
    });
  }, [queryClient, navigate]);

  return (
    <TooltipProvider delayDuration={200}>
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/" element={<SearchPage />} />
          <Route
            path="/users"
            element={
              <RequireAuth adminOnly>
                <UsersPage />
              </RequireAuth>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toaster position="top-center" richColors closeButton />
    </TooltipProvider>
  );
}
