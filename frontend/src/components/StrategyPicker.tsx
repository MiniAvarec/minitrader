import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api, StrategyListItem, StrategySelection } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const SYMBOLS = ["BTCUSDT", "ETHUSDT"];
const DEFAULT_VALUE = "__default__";

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

  async function set(symbol: string, raw: string) {
    if (raw === DEFAULT_VALUE) {
      await api.delete(`/strategies/selections/${symbol}`);
    } else {
      await api.put("/strategies/selections", {
        symbol,
        strategy_id: parseInt(raw),
        enabled: true,
      });
    }
    qc.invalidateQueries({ queryKey: ["strategy-selections"] });
  }

  async function clear(symbol: string) {
    await api.delete(`/strategies/selections/${symbol}`);
    qc.invalidateQueries({ queryKey: ["strategy-selections"] });
  }

  if (!strategies.data || !selections.data)
    return (
      <div className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
        loading…
      </div>
    );

  const selBySymbol: Record<string, StrategySelection> = {};
  for (const s of selections.data) selBySymbol[s.symbol] = s;

  return (
    <div className="flex flex-col gap-2">
      {SYMBOLS.map((sym) => {
        const sel = selBySymbol[sym];
        return (
          <div key={sym} className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold tracking-wider w-20">
              {sym}
            </span>
            <Select
              value={sel ? String(sel.strategy_id) : DEFAULT_VALUE}
              onValueChange={(v) => set(sym, v)}
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
                onClick={() => clear(sym)}
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
