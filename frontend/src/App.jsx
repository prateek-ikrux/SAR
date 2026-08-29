import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import { setUnauthorizedHandler } from "@/lib/api";
import { meKey, useMe } from "@/hooks/useAuth";
import AppShell from "@/components/AppShell";
import SignInPage from "@/pages/SignInPage";
import SearchPage from "@/pages/SearchPage";
import UsersPage from "@/pages/UsersPage";
import SettingsPage from "@/pages/SettingsPage";

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
  // session is simply over: clear it and let RequireAuth route to sign-in.
  useEffect(() => {
    setUnauthorizedHandler(() => {
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
          <Route
            path="/settings"
            element={
              <RequireAuth adminOnly>
                <SettingsPage />
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
