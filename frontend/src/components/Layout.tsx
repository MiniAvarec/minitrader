import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded ${isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"}`;

export default function Layout() {
  const { me, logout } = useAuth();
  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <span className="font-semibold">trader</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={link}>
              Dashboard
            </NavLink>
            <NavLink to="/signals" className={link}>
              Signals
            </NavLink>
            <NavLink to="/positions" className={link}>
              Positions
            </NavLink>
            <NavLink to="/strategies" className={link}>
              Strategies
            </NavLink>
            <NavLink to="/settings" className={link}>
              Settings
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-xs px-2 py-1 rounded ${
              me?.mode === "auto_execute"
                ? "bg-rose-700/30 text-rose-300"
                : "bg-emerald-700/30 text-emerald-300"
            }`}
          >
            {me?.mode === "auto_execute" ? "AUTO-EXECUTE" : "SIGNAL-ONLY"}
          </span>
          <span className="text-sm text-zinc-400">{me?.email}</span>
          <button
            onClick={logout}
            className="text-sm px-2 py-1 border border-zinc-700 rounded hover:bg-zinc-800"
          >
            Logout
          </button>
        </div>
      </header>
      <main className="flex-1 p-4">
        <Outlet />
      </main>
    </div>
  );
}
