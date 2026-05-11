import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import {
  api,
  getWatchlist,
  StrategyListItem,
  StrategySelection,
  WatchlistEntry,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const DEFAULT_VALUE = "__default__";

function key(exchange: string, symbol: string) {
  return `${exchange}:${symbol}`;
}

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
  const watchlist = useQuery<WatchlistEntry[]>({
    queryKey: ["watchlist"],
    queryFn: getWatchlist,
  });

  async function set(exchange: string, symbol: string, raw: string) {
    if (raw === DEFAULT_VALUE) {
      await api.delete(`/strategies/selections/${exchange}/${symbol}`);
    } else {
      await api.put("/strategies/selections", {
        exchange,
        symbol,
        strategy_id: parseInt(raw),
        enabled: true,
      });
    }
    qc.invalidateQueries({ queryKey: ["strategy-selections"] });
  }

  async function clear(exchange: string, symbol: string) {
    await api.delete(`/strategies/selections/${exchange}/${symbol}`);
    qc.invalidateQueries({ queryKey: ["strategy-selections"] });
  }

  if (!strategies.data || !selections.data || !watchlist.data)
    return (
      <div className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
        loading…
      </div>
    );

  if (watchlist.data.length === 0) {
    return (
      <div className="text-xs text-muted-foreground">
        Add a pair to assign strategies.
      </div>
    );
  }

  const selByKey: Record<string, StrategySelection> = {};
  for (const s of selections.data) selByKey[key(s.exchange, s.symbol)] = s;

  return (
    <div className="flex flex-col gap-2">
      {watchlist.data.map((p) => {
        const sel = selByKey[key(p.exchange, p.symbol)];
        return (
          <div key={key(p.exchange, p.symbol)} className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold tracking-wider w-24 truncate">
              <span className="text-muted-foreground">{p.exchange}·</span>
              {p.symbol}
            </span>
            <Select
              value={sel ? String(sel.strategy_id) : DEFAULT_VALUE}
              onValueChange={(v) => set(p.exchange, p.symbol, v)}
            >
              <SelectTrigger className="flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEFAULT_VALUE}>
                  default · Multi-TF Confluence
                </SelectItem>
                {strategies.data!.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.is_builtin ? "★ " : "• "}
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {sel && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => clear(p.exchange, p.symbol)}
              >
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
