import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Newspaper, TrendingDown, TrendingUp, X } from "lucide-react";
import AddPairDialog from "@/components/AddPairDialog";
import Chart from "@/components/Chart";
import FearGreedBadge from "@/components/FearGreedBadge";
import NewsPanel from "@/components/NewsPanel";
import SignalFeed from "@/components/SignalFeed";
import StrategyPicker from "@/components/StrategyPicker";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLive } from "@/lib/useLive";
import { api, getWatchlist, removeWatchlist, WatchlistEntry } from "@/api/client";
import { cn } from "@/lib/utils";

type KlineRow = { open_time: number; open: number; high: number; low: number; close: number };

type Pair = { exchange: string; symbol: string };

function WatchlistRow({
  entry,
  active,
  onSelect,
  onRemove,
}: {
  entry: WatchlistEntry;
  active: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const { data } = useQuery<{ klines: KlineRow[] }>({
    queryKey: ["klines", entry.exchange, entry.symbol, "1h"],
    queryFn: async () =>
      (await api.get(`/klines/${entry.exchange}/${entry.symbol}/1h`)).data,
    refetchInterval: 60_000,
  });

  const last = data?.klines.at(-1);
  const first = data?.klines[0];
  const chg = last && first ? ((last.close - first.open) / first.open) * 100 : 0;
  const up = chg >= 0;

  return (
    <div
      className={cn(
        "group relative flex w-full flex-col gap-1 rounded-md border p-3 text-left transition-colors",
        active
          ? "border-primary bg-primary/5"
          : "border-border bg-card hover:bg-muted/30",
      )}
    >
      <button
        onClick={onRemove}
        className="absolute right-1.5 top-1.5 hidden h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-muted/40 hover:text-foreground group-hover:flex"
        aria-label="Remove pair"
      >
        <X className="h-3 w-3" />
      </button>
      <button onClick={onSelect} className="flex flex-col gap-1 text-left">
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm font-semibold tracking-wider">
            <span className="mr-1 text-[10px] uppercase text-muted-foreground">
              {entry.exchange}
            </span>
            {entry.symbol}
          </span>
          {up ? (
            <TrendingUp className="h-3.5 w-3.5 text-success" />
          ) : (
            <TrendingDown className="h-3.5 w-3.5 text-destructive" />
          )}
        </div>
        <div className="num text-lg font-semibold">
          {last ? last.close.toFixed(2) : "—"}
        </div>
        <div
          className={cn(
            "num text-xs",
            up ? "text-success" : "text-destructive",
          )}
        >
          {up ? "+" : ""}
          {chg.toFixed(2)}%
          <span className="ml-1 text-muted-foreground text-[10px] uppercase tracking-wider">
            24h
          </span>
        </div>
      </button>
    </div>
  );
}

export default function Dashboard() {
  const live = useLive();
  const qc = useQueryClient();
  const { data: watchlist = [] } = useQuery<WatchlistEntry[]>({
    queryKey: ["watchlist"],
    queryFn: getWatchlist,
  });
  const [selected, setSelected] = useState<Pair | null>(null);

  // Default selection to the first watched pair once data lands.
  useEffect(() => {
    if (!selected && watchlist.length > 0) {
      setSelected({ exchange: watchlist[0].exchange, symbol: watchlist[0].symbol });
    }
  }, [watchlist, selected]);

  const remove = useMutation({
    mutationFn: ({ exchange, symbol }: Pair) => removeWatchlist(exchange, symbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  return (
    <div className="grid h-full grid-cols-12 gap-3">
      {/* Watchlist */}
      <div className="col-span-12 lg:col-span-3 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              Watchlist
            </div>
            <FearGreedBadge />
          </div>
          <AddPairDialog />
        </div>
        <div className="flex flex-row gap-2 lg:flex-col">
          {watchlist.length === 0 && (
            <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
              No pairs yet. Click <span className="font-semibold">Add pair</span> to begin.
            </div>
          )}
          {watchlist.map((entry) => (
            <WatchlistRow
              key={`${entry.exchange}:${entry.symbol}`}
              entry={entry}
              active={
                selected?.exchange === entry.exchange && selected?.symbol === entry.symbol
              }
              onSelect={() =>
                setSelected({ exchange: entry.exchange, symbol: entry.symbol })
              }
              onRemove={() => {
                remove.mutate({ exchange: entry.exchange, symbol: entry.symbol });
                if (
                  selected?.exchange === entry.exchange &&
                  selected?.symbol === entry.symbol
                ) {
                  setSelected(null);
                }
              }}
            />
          ))}
        </div>
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mt-2">
          Strategy per pair
        </div>
        <Card>
          <CardContent className="p-3">
            <StrategyPicker />
          </CardContent>
        </Card>
      </div>

      {/* Main chart */}
      <div className="col-span-12 lg:col-span-6 flex flex-col">
        <Card className="flex flex-1 flex-col">
          <CardContent className="flex flex-1 flex-col p-3">
            {selected ? (
              <Chart exchange={selected.exchange} symbol={selected.symbol} height={520} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Add a pair to view its chart.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Right rail: tabs */}
      <div className="col-span-12 lg:col-span-3 flex flex-col gap-2 min-h-0">
        <Tabs defaultValue="signals" className="flex flex-1 flex-col">
          <TabsList className="w-full">
            <TabsTrigger value="signals" className="flex-1">
              <Activity className="mr-1.5 h-3 w-3" /> Signals
            </TabsTrigger>
            <TabsTrigger value="news" className="flex-1">
              <Newspaper className="mr-1.5 h-3 w-3" /> News
            </TabsTrigger>
          </TabsList>
          <TabsContent value="signals" className="mt-2 flex-1 overflow-auto">
            <SignalFeed live={live} compact />
          </TabsContent>
          <TabsContent value="news" className="mt-2 flex-1 overflow-auto">
            <NewsPanel />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
