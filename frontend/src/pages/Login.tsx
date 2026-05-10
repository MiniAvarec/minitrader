import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth";

export default function Login() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await api.post(`/auth/${mode}`, { email, password });
      await refresh();
      nav("/", { replace: true });
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <form
        onSubmit={submit}
        className="bg-zinc-900 p-6 rounded-lg w-80 flex flex-col gap-3 border border-zinc-800"
      >
        <div className="text-lg font-semibold">{mode === "login" ? "Sign in" : "Register"}</div>
        <input
          type="email"
          placeholder="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2 outline-none"
        />
        <input
          type="password"
          placeholder="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2 outline-none"
        />
        {err && <div className="text-sm text-rose-400">{err}</div>}
        <button
          disabled={busy}
          className="bg-emerald-700 hover:bg-emerald-600 rounded px-3 py-2 disabled:opacity-60"
        >
          {busy ? "…" : mode === "login" ? "Sign in" : "Register"}
        </button>
        <button
          type="button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="text-sm text-zinc-400 hover:text-zinc-200"
        >
          {mode === "login" ? "Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
