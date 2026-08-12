"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function Header() {
  const { auth, logout } = useAuth();
  const router = useRouter();

  return (
    <header className="flex items-center justify-between border-b px-4 py-3 sm:px-6">
      <div className="font-semibold">SAR Profile Search</div>
      <div className="flex items-center gap-3">
        {auth && (
          <span className="hidden text-sm text-muted-foreground sm:inline">{auth.email}</span>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            logout();
            router.replace("/login");
          }}
        >
          <LogOut className="size-4" />
          Log out
        </Button>
      </div>
    </header>
  );
}
