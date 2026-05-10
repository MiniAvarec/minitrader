import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, RiskCfg } from "../api/client";
import { useAuth } from "../auth";
import StrategyPicker from "../components/StrategyPicker";

export default function Settings() {
  const { me, refresh } = useAuth();
  const qc = useQueryClient();

  // --- API keys
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [testnet, setTestnet] = useState(true);
  const [keyMsg, setKeyMsg] = useState<string | null>(null);

  const keys = useQuery({
    queryKey: ["keys"],
    queryFn: async () => (await api.get("/keys")).data,
  });

  async function saveKey() {
    setKeyMsg(null);
    try {
      const t = await api.post("/keys/test", {
        exchange: "binance",
        api_key: apiKey,
        api_secret: apiSecret,
        testnet,
      });
      await api.put("/keys", {
        exchange: "binance",
        api_key: apiKey,
        api_secret: apiSecret,
        testnet,
      });
      setKeyMsg(`saved · USDT balance $${t.data.usdt_balance.toFixed(2)}`);
      setApiKey("");
      setApiSecret("");
      qc.invalidateQueries({ queryKey: ["keys"] });
    } catch (e: any) {
      setKeyMsg(e?.response?.data?.detail || "failed");
    }
  }

  async function deleteKey() {
    await api.delete("/keys/binance");
    qc.invalidateQueries({ queryKey: ["keys"] });
  }

  // --- Risk
  const risk = useQuery<RiskCfg>({
    queryKey: ["risk"],
    queryFn: async () => (await api.get("/settings/risk")).data,
  });
  const [r, setR] = useState<RiskCfg | null>(null);
  useEffect(() => {
    if (risk.data) setR(risk.data);
  }, [risk.data]);

  async function saveRisk() {
    if (!r) return;
    await api.put("/settings/risk", r);
    qc.invalidateQueries({ queryKey: ["risk"] });
  }

  // --- Mode
  async function setMode(mode: "signal_only" | "auto_execute") {
    await api.put("/settings/mode", { mode });
    await refresh();
  }

  // --- Telegram
  const [linkToken, setLinkToken] = useState<string | null>(null);
  async function linkTelegram() {
    const r = await api.post<{ link_token: string }>("/settings/telegram/link");
    setLinkToken(r.data.link_token);
  }
  async function unlinkTelegram() {
    await api.delete("/settings/telegram");
    await refresh();
    setLinkToken(null);
  }

  return (
    <div className="grid grid-cols-1 gap-6 max-w-2xl">
      <section className="border border-zinc-800 rounded p-4">
        <h2 className="font-semibold mb-2">Strategy per symbol</h2>
        <p className="text-xs text-zinc-500 mb-3">
          Pick which strategy fires for each tracked symbol. Leave on default
          to use the built-in <em>Multi-TF Confluence</em>.
        </p>
        <StrategyPicker />
      </section>

      <section className="border border-zinc-800 rounded p-4">
        <h2 className="font-semibold mb-2">Trading mode</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setMode("signal_only")}
            className={`px-3 py-1 rounded ${
              me?.mode === "signal_only" ? "bg-emerald-700" : "bg-zinc-800"
            }`}
          >
            Signal only
          </button>
          <button
            onClick={() => setMode("auto_execute")}
            className={`px-3 py-1 rounded ${
              me?.mode === "auto_execute" ? "bg-rose-700" : "bg-zinc-800"
            }`}
          >
            Auto-execute
          </button>
        </div>
        <p className="text-xs text-zinc-500 mt-2">
          Auto-execute places real orders for every signal that passes risk checks. Use testnet first.
        </p>
      </section>

      <section className="border border-zinc-800 rounded p-4">
        <h2 className="font-semibold mb-2">Binance API key</h2>
        <p className="text-xs text-zinc-500 mb-3">
          Use a futures-enabled, IP-whitelisted key with no withdrawal permission.
          Toggle testnet ON to use testnet.binancefuture.com.
        </p>
        <div className="flex flex-col gap-2">
          <input
            placeholder="API key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2"
          />
          <input
            placeholder="API secret"
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            className="bg-zinc-950 border border-zinc-700 rounded px-3 py-2"
          />
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={testnet}
              onChange={(e) => setTestnet(e.target.checked)}
            />
            Use Binance testnet
          </label>
          <div className="flex gap-2">
            <button onClick={saveKey} className="bg-emerald-700 px-3 py-1 rounded">
              Test & save
            </button>
            <button onClick={deleteKey} className="bg-zinc-800 px-3 py-1 rounded">
              Remove
            </button>
          </div>
          {keyMsg && <div className="text-sm text-zinc-300">{keyMsg}</div>}
          <div className="text-xs text-zinc-500">
            Stored:{" "}
            {keys.data
              ? keys.data
                  .filter((k: any) => k.has_key)
                  .map((k: any) => `${k.exchange}${k.testnet ? " (testnet)" : ""}`)
                  .join(", ") || "none"
              : "…"}
          </div>
        </div>
      </section>

      <section className="border border-zinc-800 rounded p-4">
        <h2 className="font-semibold mb-2">Risk controls</h2>
        {r && (
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">
              Per-trade max notional (USDT)
              <input
                type="number"
                value={r.max_notional_usdt}
                onChange={(e) =>
                  setR({ ...r, max_notional_usdt: parseFloat(e.target.value) || 0 })
                }
                className="w-full bg-zinc-950 border border-zinc-700 rounded px-2 py-1 mt-1"
              />
            </label>
            <label className="text-sm">
              Daily loss limit (USDT)
              <input
                type="number"
                value={r.daily_loss_limit_usdt}
                onChange={(e) =>
                  setR({ ...r, daily_loss_limit_usdt: parseFloat(e.target.value) || 0 })
                }
                className="w-full bg-zinc-950 border border-zinc-700 rounded px-2 py-1 mt-1"
              />
            </label>
            <label className="text-sm">
              Max concurrent positions
              <input
                type="number"
                value={r.max_concurrent_positions}
                onChange={(e) =>
                  setR({
                    ...r,
                    max_concurrent_positions: parseInt(e.target.value, 10) || 0,
                  })
                }
                className="w-full bg-zinc-950 border border-zinc-700 rounded px-2 py-1 mt-1"
              />
            </label>
            <label className="text-sm flex items-center gap-2 mt-6">
              <input
                type="checkbox"
                checked={r.require_sl_tp}
                onChange={(e) => setR({ ...r, require_sl_tp: e.target.checked })}
              />
              Require SL/TP for auto-execute
            </label>
            <button
              onClick={saveRisk}
              className="col-span-2 bg-emerald-700 px-3 py-1 rounded mt-2"
            >
              Save risk config
            </button>
          </div>
        )}
      </section>

      <section className="border border-zinc-800 rounded p-4">
        <h2 className="font-semibold mb-2">Telegram</h2>
        {me?.telegram_chat_id ? (
          <div className="flex items-center gap-3">
            <span className="text-sm text-zinc-300">
              Linked to chat <code>{me.telegram_chat_id}</code>
            </span>
            <button onClick={unlinkTelegram} className="bg-zinc-800 px-3 py-1 rounded">
              Unlink
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <button onClick={linkTelegram} className="bg-emerald-700 px-3 py-1 rounded w-fit">
              Generate link token
            </button>
            {linkToken && (
              <div className="text-sm">
                In Telegram, message the bot:{" "}
                <code className="bg-zinc-800 px-2 py-0.5 rounded">/start {linkToken}</code>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
