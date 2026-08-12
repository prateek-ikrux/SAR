"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { auth, isReady } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isReady && !auth) router.replace("/login");
  }, [isReady, auth, router]);

  if (!isReady || !auth) return null;

  return <>{children}</>;
}

export function RedirectIfAuthed({ children }: { children: React.ReactNode }) {
  const { auth, isReady } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isReady && auth) router.replace("/");
  }, [isReady, auth, router]);

  if (!isReady || auth) return null;

  return <>{children}</>;
}
