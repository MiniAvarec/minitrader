import { Outlet, useLocation } from "react-router-dom";
import { ChevronRight, LogOut, User } from "lucide-react";
import { useAuth } from "@/auth";
import { AppSidebar } from "@/components/AppSidebar";
import { StatusBar } from "@/components/StatusBar";
import { CommandMenu } from "@/components/CommandMenu";
import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarProvider } from "@/components/ui/sidebar";

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/signals": "Signals",
  "/positions": "Positions",
  "/strategies": "Strategies",
  "/settings": "Settings",
};

function pageTitle(path: string) {
  if (PAGE_TITLES[path]) return PAGE_TITLES[path];
  if (path.startsWith("/strategies/")) return "Strategy Editor";
  return "";
}

function HeaderInner() {
  const { me, logout } = useAuth();
  const location = useLocation();
  const auto = me?.mode === "auto_execute";

  return (
    <header className="flex h-14 items-center gap-3 border-b border-border bg-card px-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="font-mono uppercase tracking-wider">
          {pageTitle(location.pathname)}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <button
          className="hidden md:flex h-8 items-center gap-2 rounded-md border border-border bg-background px-2.5 text-xs text-muted-foreground hover:bg-muted/50"
          onClick={() => {
            const ev = new KeyboardEvent("keydown", { key: "k", metaKey: true });
            document.dispatchEvent(ev);
          }}
        >
          <span>Quick search…</span>
          <kbd className="pointer-events-none ml-2 rounded border border-border bg-muted px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
            ⌘K
          </kbd>
        </button>

        <ThemeToggle />

        <Badge variant={auto ? "destructive" : "success"}>
          {auto ? "AUTO-EXEC" : "SIGNAL-ONLY"}
        </Badge>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <User className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>Account</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled className="font-mono text-xs">
              {me?.email}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => logout()}>
              <LogOut /> Logout
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

function Breadcrumb() {
  const location = useLocation();
  const parts = location.pathname.split("/").filter(Boolean);
  if (parts.length === 0) return null;
  return (
    <div className="flex h-8 items-center gap-1 border-b border-border bg-background px-4 text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
      <span>/</span>
      {parts.map((p, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3 w-3" />}
          <span>{p}</span>
        </span>
      ))}
    </div>
  );
}

export default function Layout() {
  return (
    <SidebarProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        <AppSidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <HeaderInner />
          <Breadcrumb />
          <main className="flex-1 overflow-auto p-4">
            <Outlet />
          </main>
          <StatusBar />
        </div>
      </div>
      <CommandMenu />
    </SidebarProvider>
  );
}
