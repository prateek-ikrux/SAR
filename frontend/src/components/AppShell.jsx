import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { LogOut, Monitor, Moon, Search, Sun, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import Logo from "@/components/Logo";
import { useLogout, useMe } from "@/hooks/useAuth";
import { useUiStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";

const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

function NavLink({ to, icon: Icon, children }) {
  const { pathname } = useLocation();
  const active = pathname === to;
  return (
    <Link
      to={to}
      className={cn(
        "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
        active
          ? "bg-secondary text-secondary-foreground font-medium"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      <Icon className="size-4" />
      {children}
    </Link>
  );
}

export default function AppShell() {
  const { data: user } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const { theme, setTheme } = useUiStore();

  const initials = (user?.name || user?.email || "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  function signOut() {
    logout();
    toast.success("Signed out");
    navigate("/sign-in", { replace: true });
  }

  return (
    <div className="min-h-svh bg-background">
      <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
          <Link to="/" className="shrink-0">
            <Logo />
          </Link>

          <Separator orientation="vertical" className="h-5" />

          <nav className="flex items-center gap-1">
            <NavLink to="/" icon={Search}>
              Search
            </NavLink>
            {user?.role === "admin" && (
              <NavLink to="/users" icon={Users}>
                Users
              </NavLink>
            )}
          </nav>

          <div className="flex-1" />

          <DropdownMenu>
            {/* Base UI merges via `render`, not `asChild` - the Radix prop would
                leave a <button> nested inside a <button>. */}
            <DropdownMenuTrigger
              render={
                <Button variant="ghost" size="sm" className="gap-2" aria-label="Account menu" />
              }
            >
              <span
                aria-hidden="true"
                className="flex size-6 items-center justify-center rounded-full bg-secondary text-[11px] font-medium"
              >
                {initials}
              </span>
              <span className="hidden text-sm sm:inline">{user?.name || user?.email}</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              {/* Base UI requires GroupLabel to sit inside a Group. Without the
                  wrapper it throws and the whole menu fails to render. */}
              <div className="px-2 py-1.5">
                <div className="truncate text-sm font-medium">{user?.name}</div>
                <div className="truncate text-xs text-muted-foreground">{user?.email}</div>
                <div className="mt-1 text-xs text-muted-foreground capitalize">{user?.role}</div>
              </div>

              <DropdownMenuSeparator />

              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                  Theme
                </DropdownMenuLabel>
                {THEMES.map(({ value, label, icon: Icon }) => (
                  <DropdownMenuItem key={value} onClick={() => setTheme(value)}>
                    <Icon className="size-4" />
                    {label}
                    {theme === value && <span className="ml-auto text-xs">•</span>}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>

              <DropdownMenuSeparator />

              <DropdownMenuItem onClick={signOut}>
                <LogOut className="size-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
