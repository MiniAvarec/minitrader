import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, SignalRow } from "../api/client";

function fmt(n: number | null | undefined, d = 2) {
  return n == null ? "—" : n.toFixed(d);
}

export default function SignalFeed({ live }: { live: any | null }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<SignalRow[]>({
    queryKey: ["signals"],
    queryFn: async () => (await api.get("/signals?limit=50")).data,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (live && live.event === "signal") {
      qc.invalidateQueries({ queryKey: ["signals"] });
    }
  }, [live, qc]);

  async function execute(id: number) {
    try {
      const r = await api.post("/orders/execute", { signal_id: id });
      if (r.data.ok) alert(`order placed: ${r.data.exchange_order_id ?? r.data.order_id}`);
      else alert(`refused: ${r.data.reason}`);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "failed");
    }
  }

  if (isLoading) return <div>loading…</div>;

  return (
    <div className="flex flex-col gap-2">
      {(data ?? []).map((s) => (
        <div
          key={s.id}
          className="border border-zinc-800 rounded p-3 bg-zinc-900 grid grid-cols-12 gap-3 items-center"
        >
          <div className="col-span-2 flex items-center gap-2">
            <span
              className={`px-2 py-0.5 rounded text-xs font-bold ${
                s.side === "buy" ? "bg-emerald-700 text-white" : "bg-rose-700 text-white"
              }`}
            >
              {s.side.toUpperCase()}
            </span>
            <div className="flex flex-col leading-tight min-w-0">
              <span className="font-mono">{s.symbol}</span>
              {s.strategy_name && (
                <span className="text-[10px] text-zinc-500 truncate">{s.strategy_name}</span>
              )}
            </div>
          </div>
          <div className="col-span-1 text-sm">conf {s.confidence.toFixed(0)}</div>
          <div className="col-span-2 text-sm">entry <span className="font-mono">{fmt(s.entry, 2)}</span></div>
          <div className="col-span-1 text-sm">SL <span className="font-mono">{fmt(s.sl, 2)}</span></div>
          <div className="col-span-1 text-sm">TP <span className="font-mono">{fmt(s.tp, 2)}</span></div>
          <div className="col-span-3 text-xs text-zinc-400 flex flex-wrap gap-1">
            {s.breakdown.map((b) => (
              <span
                key={b.tf}
                className={`px-1.5 py-0.5 rounded ${
                  b.vote > 0
                    ? "bg-emerald-900/60 text-emerald-300"
                    : b.vote < 0
                    ? "bg-rose-900/60 text-rose-300"
                    : "bg-zinc-800 text-zinc-400"
                }`}
                title={`RSI ${fmt(b.rsi)} MACDh ${fmt(b.macd_hist)}`}
              >
                {b.tf}
              </span>
            ))}
          </div>
          <div className="col-span-2 flex justify-end gap-2">
            <button
              onClick={() => execute(s.id)}
              disabled={s.status !== "new" && s.status !== "dispatched"}
              className="text-xs bg-zinc-100 text-zinc-900 px-2 py-1 rounded disabled:opacity-50"
            >
              Execute
            </button>
            <span className="text-xs text-zinc-500 self-center">{s.status}</span>
          </div>
          {s.news_refs.length > 0 && (
            <div className="col-span-12 text-xs text-zinc-400 mt-1">
              {s.news_refs.map((n, i) => (
                <a
                  key={i}
                  href={n.url}
                  target="_blank"
                  rel="noreferrer"
                  className="underline mr-2"
                >
                  {n.headline}
                </a>
              ))}
            </div>
          )}
        </div>
      ))}
      {data && data.length === 0 && (
        <div className="text-zinc-500 text-sm">No signals yet — they appear as soon as the engine fires.</div>
      )}
    </div>
  );
}
