import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, StrategyListItem, StrategySelection } from "../api/client";

const SYMBOLS = ["BTCUSDT", "ETHUSDT"];

export default function StrategyPicker() {
  const qc = useQueryClient();
  const strategies = useQuery<StrategyListItem[]>({
    queryKey: ["strategies"],
    queryFn: async () => (await api.get("/strategies")).data,
  });
  const selections = useQuery<StrategySelection[]>({
    queryKey: ["strategy-selections"],
    queryFn: async () => (await api.get("/strategies/selections")).data,
  });

  async function set(symbol: string, strategy_id: number) {
    await api.put("/strategies/selections", { symbol, strategy_id, enabled: true });
    qc.invalidateQueries({ queryKey: ["strategy-selections"] });
  }
  async function clear(symbol: string) {
    await api.delete(`/strategies/selections/${symbol}`);
    qc.invalidateQueries({ queryKey: ["strategy-selections"] });
  }

  if (!strategies.data || !selections.data) return <div className="text-sm">…</div>;
  const byId: Record<number, StrategyListItem> = {};
  for (const s of strategies.data) byId[s.id] = s;
  const selBySymbol: Record<string, StrategySelection> = {};
  for (const s of selections.data) selBySymbol[s.symbol] = s;

  return (
    <div className="grid grid-cols-1 gap-2">
      {SYMBOLS.map((sym) => {
        const sel = selBySymbol[sym];
        return (
          <div key={sym} className="flex items-center gap-2">
            <span className="font-mono w-24">{sym}</span>
            <select
              value={sel?.strategy_id ?? ""}
              onChange={(e) =>
                e.target.value ? set(sym, parseInt(e.target.value)) : clear(sym)
              }
              className="bg-zinc-950 border border-zinc-700 rounded px-2 py-1 flex-1"
            >
              <option value="">(default: Multi-TF Confluence)</option>
              {strategies.data!.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.is_builtin ? "★ " : "• "}
                  {s.name}
                </option>
              ))}
            </select>
            {sel && (
              <button
                onClick={() => clear(sym)}
                className="text-xs px-2 py-1 border border-zinc-700 rounded"
              >
                Reset
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
