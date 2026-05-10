import * as React from "react";
import { PanelLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type SidebarState = "expanded" | "collapsed";

type SidebarContext = {
  state: SidebarState;
  toggle: () => void;
  setState: (s: SidebarState) => void;
};

const Ctx = React.createContext<SidebarContext | null>(null);

const STORAGE_KEY = "mt-sidebar-state";

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [state, setStateRaw] = React.useState<SidebarState>(() => {
    if (typeof window === "undefined") return "expanded";
    return (localStorage.getItem(STORAGE_KEY) as SidebarState | null) ?? "expanded";
  });

  const setState = React.useCallback((s: SidebarState) => {
    setStateRaw(s);
    if (typeof window !== "undefined") localStorage.setItem(STORAGE_KEY, s);
  }, []);

  const toggle = React.useCallback(() => {
    setState(state === "expanded" ? "collapsed" : "expanded");
  }, [state, setState]);

  return (
    <Ctx.Provider value={{ state, toggle, setState }}>{children}</Ctx.Provider>
  );
}

export function useSidebar() {
  const c = React.useContext(Ctx);
  if (!c) throw new Error("useSidebar must be used inside <SidebarProvider>");
  return c;
}

export function Sidebar({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const { state } = useSidebar();
  return (
    <aside
      data-state={state}
      className={cn(
        "group/sidebar shrink-0 border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out flex flex-col",
        state === "expanded" ? "w-56" : "w-14",
        className,
      )}
    >
      {children}
    </aside>
  );
}

export function SidebarHeader({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex h-14 items-center gap-2 border-b border-sidebar-border px-3",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SidebarContent({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return <div className={cn("flex-1 overflow-y-auto py-2", className)}>{children}</div>;
}

export function SidebarFooter({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("border-t border-sidebar-border p-2", className)}>{children}</div>
  );
}

export function SidebarMenu({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <nav className={cn("flex flex-col gap-0.5 px-2", className)}>{children}</nav>
  );
}

export function SidebarMenuItem({
  active,
  icon,
  label,
  onClick,
}: {
  active?: boolean;
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) {
  const { state } = useSidebar();
  return (
    <button
      onClick={onClick}
      data-active={active ? "true" : undefined}
      className={cn(
        "group/item flex h-9 items-center gap-3 rounded-md px-2 text-sm font-medium transition-colors",
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        active &&
          "bg-sidebar-accent text-sidebar-accent-foreground shadow-[inset_3px_0_0_hsl(var(--sidebar-primary))]",
        state === "collapsed" && "justify-center px-0",
      )}
      title={state === "collapsed" ? label : undefined}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center [&_svg]:h-[18px] [&_svg]:w-[18px]">
        {icon}
      </span>
      {state === "expanded" && <span className="truncate">{label}</span>}
    </button>
  );
}

export function SidebarTrigger({ className }: { className?: string }) {
  const { toggle } = useSidebar();
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      className={cn("h-7 w-7", className)}
      aria-label="Toggle sidebar"
    >
      <PanelLeft className="h-4 w-4" />
    </Button>
  );
}
