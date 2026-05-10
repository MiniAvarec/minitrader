import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, Me } from "./api/client";

type Ctx = {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx>({
  me: null,
  loading: true,
  refresh: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const r = await api.get<Me>("/auth/me");
      setMe(r.data);
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await api.post("/auth/logout");
    setMe(null);
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <AuthCtx.Provider value={{ me, loading, refresh, logout }}>{children}</AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
