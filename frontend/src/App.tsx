import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/auth";
import Layout from "@/components/Layout";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Signals from "@/pages/Signals";
import Positions from "@/pages/Positions";
import Settings from "@/pages/Settings";
import Strategies from "@/pages/Strategies";
import StrategyEdit from "@/pages/StrategyEdit";

function Protected({ children }: { children: JSX.Element }) {
  const { me, loading } = useAuth();
  if (loading)
    return (
      <div className="flex h-screen items-center justify-center text-sm font-mono uppercase tracking-wider text-muted-foreground">
        loading…
      </div>
    );
  if (!me) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="mt-theme">
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <Protected>
                <Layout />
              </Protected>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="signals" element={<Signals />} />
            <Route path="positions" element={<Positions />} />
            <Route path="strategies" element={<Strategies />} />
            <Route path="strategies/:id" element={<StrategyEdit />} />
            <Route path="settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster />
      </AuthProvider>
    </ThemeProvider>
  );
}
