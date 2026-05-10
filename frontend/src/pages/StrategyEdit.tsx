import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, BacktestResult, StrategyDetail } from "../api/client";
import StrategyEditor from "../components/StrategyEditor";
import BacktestPanel from "../components/BacktestPanel";

export default function StrategyEdit() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const qc = useQueryClient();

  const { data: strategy, isLoading } = useQuery<StrategyDetail>({
    queryKey: ["strategy", id],
    queryFn: async () => (await api.get(`/strategies/${id}`)).data,
  });

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [validateMsg, setValidateMsg] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [bt, setBt] = useState<BacktestResult | null>(null);
  const [btSymbol, setBtSymbol] = useState("BTCUSDT");
  const [btHours, setBtHours] = useState(168);
  const [btBusy, setBtBusy] = useState(false);

  useEffect(() => {
    if (strategy) {
      setCode(strategy.code);
      setName(strategy.name);
    }
  }, [strategy]);

  if (isLoading || !strategy) return <div>loading…</div>;
  const editable = !strategy.is_builtin;

  async function validate() {
    setValidateMsg(null);
    const r = await api.post("/strategies/validate", { code });
    if (r.data.ok) {
      setValidateMsg(
        `OK · name: ${r.data.name} · timeframes: ${(r.data.timeframes || []).join(", ") || "—"}`,
      );
    } else {
      setValidateMsg(`error: ${r.data.error}`);
    }
  }

  async function save() {
    setSaveMsg(null);
    try {
      await api.put(`/strategies/${id}`, { code, name });
      qc.invalidateQueries({ queryKey: ["strategies"] });
      qc.invalidateQueries({ queryKey: ["strategy", id] });
      setSaveMsg("saved");
    } catch (e: any) {
      setSaveMsg(e?.response?.data?.detail || "failed");
    }
  }

  async function runBacktest() {
    setBtBusy(true);
    setBt(null);
    try {
      const r = await api.post(`/strategies/${id}/backtest`, {
        symbol: btSymbol,
        hours: btHours,
        notional_usdt: 100,
      });
      setBt(r.data);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "backtest failed");
    } finally {
      setBtBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-12 gap-4 max-w-7xl">
      <div className="col-span-7 flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => nav("/strategies")}
            className="text-xs px-2 py-1 border border-zinc-700 rounded"
          >
            ← Back
          </button>
          <input
            disabled={!editable}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 flex-1 disabled:opacity-60"
          />
          {strategy.is_builtin && (
            <span className="text-xs px-2 py-1 bg-zinc-800 rounded">read-only built-in</span>
          )}
        </div>
        <StrategyEditor value={code} onChange={setCode} readOnly={!editable} />
        <div className="flex items-center gap-2">
          <button onClick={validate} className="text-sm px-3 py-1 border border-zinc-700 rounded">
            Validate
          </button>
          {editable && (
            <button onClick={save} className="text-sm px-3 py-1 bg-emerald-700 rounded">
              Save
            </button>
          )}
          {validateMsg && <span className="text-xs text-zinc-300">{validateMsg}</span>}
          {saveMsg && <span className="text-xs text-zinc-300">{saveMsg}</span>}
        </div>
      </div>

      <div className="col-span-5 flex flex-col gap-3">
        <div className="border border-zinc-800 rounded p-3">
          <h3 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">Backtest</h3>
          <div className="flex items-center gap-2 mb-3">
            <select
              value={btSymbol}
              onChange={(e) => setBtSymbol(e.target.value)}
              className="bg-zinc-950 border border-zinc-700 rounded px-2 py-1"
            >
              <option>BTCUSDT</option>
              <option>ETHUSDT</option>
            </select>
            <select
              value={btHours}
              onChange={(e) => setBtHours(parseInt(e.target.value))}
              className="bg-zinc-950 border border-zinc-700 rounded px-2 py-1"
            >
              <option value={24}>24h</option>
              <option value={72}>3d</option>
              <option value={168}>7d</option>
              <option value={720}>30d</option>
            </select>
            <button
              onClick={runBacktest}
              disabled={btBusy}
              className="text-sm px-3 py-1 bg-emerald-700 rounded disabled:opacity-60"
            >
              {btBusy ? "running…" : "Run"}
            </button>
          </div>
          <BacktestPanel result={bt} />
        </div>
      </div>
    </div>
  );
}
