"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { decodeJwt, isTokenExpired } from "@/lib/jwt";

const STORAGE_KEY = "sar.auth";

type AuthState = {
  email: string;
  token: string;
} | null;

type AuthContextValue = {
  auth: AuthState;
  isReady: boolean;
  login: (token: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredAuth(): AuthState {
  const token = window.localStorage.getItem(STORAGE_KEY);
  if (!token || isTokenExpired(token)) {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
  const payload = decodeJwt(token);
  if (!payload) return null;
  return { email: payload.sub, token };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    setAuth(readStoredAuth());
    setIsReady(true);
  }, []);

  const login = useCallback((token: string) => {
    window.localStorage.setItem(STORAGE_KEY, token);
    const payload = decodeJwt(token);
    setAuth(payload ? { email: payload.sub, token } : null);
  }, []);

  const logout = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setAuth(null);
  }, []);

  return (
    <AuthContext.Provider value={{ auth, isReady, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
