import { useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  BookOpen,
  Briefcase,
  BrainCircuit,
  LayoutDashboard,
  Route,
  Settings as SettingsIcon,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { useAuth } from "@/auth";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";

const ITEMS = [
  { to: "/", label: "Dashboard", icon: <LayoutDashboard /> },
  { to: "/signals", label: "Signals", icon: <Activity /> },
  { to: "/positions", label: "Positions", icon: <Briefcase /> },
  { to: "/journal", label: "Journal", icon: <BookOpen /> },
  { to: "/strategies", label: "Strategies", icon: <BrainCircuit /> },
  { to: "/tools", label: "Tools", icon: <Route /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
];

export function AppSidebar() {
  const location = useLocation();
  const nav = useNavigate();
  const { state } = useSidebar();
  const { me } = useAuth();
  const items = me?.is_admin
    ? [...ITEMS, { to: "/admin", label: "Admin", icon: <ShieldCheck /> }]
    : ITEMS;

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-primary text-primary-foreground">
          <TrendingUp className="h-4 w-4" />
        </div>
        {state === "expanded" && (
          <div className="flex flex-col leading-none">
            <span className="font-mono text-sm font-bold tracking-wider">TRADER</span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              v0.1.0
            </span>
          </div>
        )}
      </SidebarHeader>

      <SidebarContent>
        <SidebarMenu>
          {items.map((it) => {
            const active =
              it.to === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(it.to);
            return (
              <SidebarMenuItem
                key={it.to}
                active={active}
                icon={it.icon}
                label={it.label}
                onClick={() => nav(it.to)}
              />
            );
          })}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter>
        <div className="flex items-center justify-between">
          {state === "expanded" && (
            <span className="px-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              MAINNET
            </span>
          )}
          <SidebarTrigger className="ml-auto" />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
