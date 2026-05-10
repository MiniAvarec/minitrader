import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Newspaper } from "lucide-react";
import { toast } from "sonner";
import { api, SignalRow } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

function fmt(n: number | null | undefined, d = 2) {
  return n == null ? "—" : n.toFixed(d);
}

export default function SignalFeed({
  live,
  compact = false,
}: {
  live: any | null;
  compact?: boolean;
}) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<SignalRow[]>({
    queryKey: ["signals"],
    queryFn: async () => (await api.get("/signals?limit=50")).data,
    refetchInterval: 60_000,
  });
  const [openId, setOpenId] = useState<number | null>(null);

  useEffect(() => {
    if (live && live.event === "signal") {
      qc.invalidateQueries({ queryKey: ["signals"] });
    }
  }, [live, qc]);

  async function execute(id: number) {
    try {
      const r = await api.post("/orders/execute", { signal_id: id });
      if (r.data.ok)
        toast.success(`Order placed: ${r.data.exchange_order_id ?? r.data.order_id}`);
      else toast.error(`Refused: ${r.data.reason}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "failed");
    }
  }

  if (isLoading)
    return (
      <div className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
        loading…
      </div>
    );

  const rows = data ?? [];
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        No signals yet — they appear as soon as the engine fires.
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="flex flex-col divide-y divide-border rounded-md border border-border bg-card">
        {rows.map((s) => {
          const open = openId === s.id;
          const buy = s.side === "buy";
          return (
            <div key={s.id} className="flex flex-col">
              <div
                className={cn(
                  "grid items-center gap-2 px-3 py-2",
                  compact
                    ? "grid-cols-[auto_1fr_auto] gap-3"
                    : "grid-cols-[auto_minmax(0,1fr)_auto_auto_auto] gap-3",
                )}
              >
                <Badge variant={buy ? "success" : "destructive"} className="w-12 justify-center">
                  {buy ? "BUY" : "SELL"}
                </Badge>

                <div className="flex flex-col leading-tight min-w-0">
                  <span className="font-mono text-sm font-semibold tracking-wider">
                    {s.symbol}
                  </span>
                  {s.strategy_name && (
                    <span className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
                      {s.strategy_name}
                    </span>
                  )}
                </div>

                {!compact && (
                  <div className="flex items-baseline gap-3 text-xs">
                    <span className="text-muted-foreground">conf</span>
                    <span className="num text-sm font-semibold">{s.confidence.toFixed(0)}</span>
                  </div>
                )}

                {!compact && (
                  <div className="hidden md:flex items-baseline gap-2 text-xs">
                    <span className="text-muted-foreground">@</span>
                    <span className="num">{fmt(s.entry, 2)}</span>
                    {s.sl != null && (
                      <span className="text-muted-foreground num">
                        sl {fmt(s.sl, 2)}
                      </span>
                    )}
                    {s.tp != null && (
                      <span className="text-muted-foreground num">
                        tp {fmt(s.tp, 2)}
                      </span>
                    )}
                  </div>
                )}

                <div className="flex items-center gap-1">
                  {!compact && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => execute(s.id)}
                      disabled={s.status !== "new" && s.status !== "dispatched"}
                      className="h-7 text-[10px]"
                    >
                      Execute
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setOpenId(open ? null : s.id)}
                    className="h-7 w-7"
                  >
                    {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </Button>
                </div>
              </div>

              {open && (
                <div className="border-t border-border bg-muted/30 px-3 py-2 text-xs">
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {s.breakdown.map((b) => (
                      <Tooltip key={b.tf}>
                        <TooltipTrigger asChild>
                          <span
                            className={cn(
                              "rounded-sm px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider",
                              b.vote > 0
                                ? "bg-success/15 text-success"
                                : b.vote < 0
                                  ? "bg-destructive/15 text-destructive"
                                  : "bg-muted text-muted-foreground",
                            )}
                          >
                            {b.tf}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          <div className="font-mono text-[10px] uppercase tracking-wider">
                            <div>RSI {fmt(b.rsi)}</div>
                            <div>MACDh {fmt(b.macd_hist)}</div>
                            <div>EMA20 {fmt(b.ema20)}</div>
                            <div>EMA50 {fmt(b.ema50)}</div>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    ))}
                  </div>
                  {compact && (
                    <div className="flex items-baseline gap-2 num text-xs mb-2">
                      <span className="text-muted-foreground">@</span>
                      <span>{fmt(s.entry, 2)}</span>
                      {s.sl != null && (
                        <span className="text-muted-foreground">sl {fmt(s.sl, 2)}</span>
                      )}
                      {s.tp != null && (
                        <span className="text-muted-foreground">tp {fmt(s.tp, 2)}</span>
                      )}
                    </div>
                  )}
                  {s.news_refs.length > 0 && (
                    <div className="flex flex-col gap-1">
                      {s.news_refs.map((n, i) => (
                        <a
                          key={i}
                          href={n.url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-start gap-1.5 text-muted-foreground hover:text-foreground"
                        >
                          <Newspaper className="mt-0.5 h-3 w-3 shrink-0" />
                          <span className="leading-tight">{n.headline}</span>
                        </a>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                    <span>{new Date(s.created_at).toLocaleString()}</span>
                    <span>STATUS · {s.status}</span>
                  </div>
                  {compact && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => execute(s.id)}
                      disabled={s.status !== "new" && s.status !== "dispatched"}
                      className="mt-2 h-7 w-full text-[10px]"
                    >
                      Execute
                    </Button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
