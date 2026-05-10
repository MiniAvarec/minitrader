import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Newspaper, TrendingDown, TrendingUp } from "lucide-react";
import Chart from "@/components/Chart";
import NewsPanel from "@/components/NewsPanel";
import SignalFeed from "@/components/SignalFeed";
import StrategyPicker from "@/components/StrategyPicker";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLive } from "@/lib/useLive";
import { api } from "@/api/client";
import { cn } from "@/lib/utils";

const SYMBOLS = ["BTCUSDT", "ETHUSDT"];

type KlineRow = { open_time: number; open: number; high: number; low: number; close: number };

function Watchlist({
  symbol,
  active,
  onSelect,
}: {
  symbol: string;
  active: boolean;
  onSelect: () => void;
}) {
  const { data } = useQuery<{ klines: KlineRow[] }>({
    queryKey: ["klines", symbol, "1h"],
    queryFn: async () => (await api.get(`/klines/${symbol}/1h`)).data,
    refetchInterval: 60_000,
  });

  const last = data?.klines.at(-1);
  const first = data?.klines[0];
  const chg = last && first ? ((last.close - first.open) / first.open) * 100 : 0;
  const up = chg >= 0;

  return (
    <button
      onClick={onSelect}
      className={cn(
        "flex w-full flex-col gap-1 rounded-md border p-3 text-left transition-colors",
        active
          ? "border-primary bg-primary/5"
          : "border-border bg-card hover:bg-muted/30",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-sm font-semibold tracking-wider">{symbol}</span>
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
  );
}

export default function Dashboard() {
  const live = useLive();
  const [selected, setSelected] = useState<string>(SYMBOLS[0]);

  return (
    <div className="grid h-full grid-cols-12 gap-3">
      {/* Watchlist */}
      <div className="col-span-12 lg:col-span-3 flex flex-col gap-3">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          Watchlist
        </div>
        <div className="flex flex-row gap-2 lg:flex-col">
          {SYMBOLS.map((sym) => (
            <Watchlist
              key={sym}
              symbol={sym}
              active={sym === selected}
              onSelect={() => setSelected(sym)}
            />
          ))}
        </div>
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mt-2">
          Strategy per symbol
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
            <Chart symbol={selected} height={520} />
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
