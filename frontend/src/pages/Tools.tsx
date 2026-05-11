import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, GitBranch, Play, RefreshCw, Route, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  getWatchlist,
  OptimizerResult,
  RebalancePlan,
  RouteResult,
  ScenarioResult,
  StrategyListItem,
  WatchlistEntry,
} from "@/api/client";
import { useAuth } from "@/auth";
import PairBadge from "@/components/PairBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const TOOL_BLURBS: Record<string, { title: string; lede: string }> = {
  rebalancer: {
    title: "Portfolio Rebalancer",
    lede: "Reads open positions across every connected exchange and proposes reduce-only orders that bring exposure under your per-exchange and per-asset concentration caps. Preview is read-only; Execute is enabled only in auto_execute mode.",
  },
  router: {
    title: "Smart Execution Router",
    lede: "For a symbol/side/notional, polls the L2 order book on each keyed venue, simulates the market fill, and scores spread + slippage + taker fee. Picks the venue with the lowest total cost. Quote is read-only; Execute fires a market order on the winning venue (auto_execute only).",
  },
  optimizer: {
    title: "Walk-Forward Optimizer",
    lede: "Runs your strategy across a parameter grid with a train + out-of-sample validation split. Each combination is scored on validation PnL, win-rate, train/validation stability, and drawdown penalty. Use to find robust settings instead of curve-fitting one window.",
  },
  scenarios: {
    title: "Scenario Simulator",
    lede: "Applies a shock preset (gap down/up, volatility cascade, stop series, correlation spike) at the chosen magnitude to your current live positions, then projects PnL against today's realized PnL and your daily loss limit. Flags whether the shock would trip the kill-switch.",
  },
};

export default function Tools() {
  return (
    <div className="max-w-7xl flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Trading intelligence tools</h1>
        <p className="text-sm text-muted-foreground">
          Helpers that sit on top of your live positions, watchlist and strategies: balance concentration,
          pick the cheapest venue for a trade, search a strategy parameter grid, and stress-test the book against shocks.
        </p>
      </div>
      <Tabs defaultValue="rebalancer" className="flex flex-col gap-4">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="rebalancer" className="gap-2"><RefreshCw className="h-4 w-4" />Rebalancer</TabsTrigger>
          <TabsTrigger value="router" className="gap-2"><Route className="h-4 w-4" />Router</TabsTrigger>
          <TabsTrigger value="optimizer" className="gap-2"><Bot className="h-4 w-4" />Optimizer</TabsTrigger>
          <TabsTrigger value="scenarios" className="gap-2"><ShieldAlert className="h-4 w-4" />Scenarios</TabsTrigger>
        </TabsList>
        <TabsContent value="rebalancer"><Rebalancer /></TabsContent>
        <TabsContent value="router"><ExecutionRouter /></TabsContent>
        <TabsContent value="optimizer"><Optimizer /></TabsContent>
        <TabsContent value="scenarios"><Scenarios /></TabsContent>
      </Tabs>
    </div>
  );
}

function ToolIntro({ kind }: { kind: keyof typeof TOOL_BLURBS }) {
  const blurb = TOOL_BLURBS[kind];
  return (
    <Card className="col-span-12">
      <CardHeader className="space-y-1">
        <CardTitle className="text-base">{blurb.title}</CardTitle>
        <CardDescription>{blurb.lede}</CardDescription>
      </CardHeader>
    </Card>
  );
}

function Rebalancer() {
  const { me } = useAuth();
  const [maxExchange, setMaxExchange] = useState(60);
  const [maxAsset, setMaxAsset] = useState(50);
  const [minOrder, setMinOrder] = useState(10);
  const [plan, setPlan] = useState<RebalancePlan | null>(null);
  const preview = useMutation({
    mutationFn: async () => (await api.post<RebalancePlan>("/portfolio/rebalance/preview", body())).data,
    onSuccess: setPlan,
    onError: errToast,
  });
  const execute = useMutation({
    mutationFn: async () => (await api.post<RebalancePlan>("/portfolio/rebalance/execute", body())).data,
    onSuccess: (r) => {
      setPlan(r);
      toast.success("Rebalance submitted");
    },
    onError: errToast,
  });
  function body() {
    return {
      max_exchange_share: maxExchange / 100,
      max_asset_share: maxAsset / 100,
      min_order_notional_usdt: minOrder,
    };
  }
  return (
    <div className="grid grid-cols-12 gap-4">
      <ToolIntro kind="rebalancer" />
      <Card className="col-span-12 lg:col-span-4">
        <CardHeader className="space-y-1">
          <CardTitle>Inputs</CardTitle>
          <CardDescription>
            Caps as a fraction of total open notional. The plan emits reduce-only sells/buys that
            shrink any exchange or base asset above its cap. Orders below the minimum USDT are dropped.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <NumberField label="Max exchange share %" value={maxExchange} onChange={setMaxExchange} />
          <NumberField label="Max asset share %" value={maxAsset} onChange={setMaxAsset} />
          <NumberField label="Min order USDT" value={minOrder} onChange={setMinOrder} />
          <div className="flex gap-2">
            <Button onClick={() => preview.mutate()} disabled={preview.isPending}>
              <GitBranch className="mr-1 h-4 w-4" />Preview
            </Button>
            <Button
              variant="destructive"
              disabled={!plan || me?.mode !== "auto_execute" || execute.isPending}
              onClick={() => execute.mutate()}
            >
              <Play className="mr-1 h-4 w-4" />Execute
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card className="col-span-12 lg:col-span-8">
        <CardHeader className="space-y-1">
          <CardTitle>Plan</CardTitle>
          <CardDescription>
            Total exposure across all venues, number of generated reduce-only orders, and per-position
            reasons (which cap was exceeded). Run id is saved in the audit log.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {plan ? (
            <>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Stat label="Exposure" value={`$${plan.total_exposure_usdt.toFixed(2)}`} />
                <Stat label="Orders" value={String(plan.intents.length)} />
                <Stat label="Mode" value={plan.can_execute ? "AUTO" : "SIGNAL"} />
                <Stat label="Run" value={`#${plan.run_id}`} />
              </div>
              <IntentTable intents={plan.intents} />
            </>
          ) : <Empty />}
        </CardContent>
      </Card>
    </div>
  );
}

function ExecutionRouter() {
  const { me } = useAuth();
  const watchlist = useQuery<WatchlistEntry[]>({ queryKey: ["watchlist"], queryFn: getWatchlist });
  const [pair, setPair] = useFirstPair(watchlist.data ?? []);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [notional, setNotional] = useState(50);
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [result, setResult] = useState<RouteResult | null>(null);
  const payload = () => {
    const [, symbol = ""] = pair.split(":");
    return {
      symbol,
      side,
      notional_usdt: notional,
      sl: sl ? Number(sl) : null,
      tp: tp ? Number(tp) : null,
    };
  };
  const quote = useMutation({
    mutationFn: async () => (await api.post<RouteResult>("/execution/route", payload())).data,
    onSuccess: setResult,
    onError: errToast,
  });
  const execute = useMutation({
    mutationFn: async () => (await api.post<RouteResult>("/execution/route/execute", payload())).data,
    onSuccess: (r) => {
      setResult(r);
      toast.success(r.execution?.ok ? "Order submitted" : r.execution?.reason || "Route checked");
    },
    onError: errToast,
  });
  return (
    <div className="grid grid-cols-12 gap-4">
      <ToolIntro kind="router" />
      <Card className="col-span-12 lg:col-span-4">
        <CardHeader className="space-y-1">
          <CardTitle>Order</CardTitle>
          <CardDescription>
            Choose a watchlist pair, side and USDT notional. Optional SL/TP are attached when the route
            is executed. Quote returns scored venues; Execute fires a MARKET order on the best one.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <PairSelect value={pair} onChange={setPair} watchlist={watchlist.data ?? []} />
          <div className="grid grid-cols-2 gap-2">
            <Select value={side} onValueChange={(v) => setSide(v as "buy" | "sell")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="buy">Buy</SelectItem><SelectItem value="sell">Sell</SelectItem></SelectContent>
            </Select>
            <NumberField label="Notional" value={notional} onChange={setNotional} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <TextField label="SL" value={sl} onChange={setSl} />
            <TextField label="TP" value={tp} onChange={setTp} />
          </div>
          <div className="flex gap-2">
            <Button onClick={() => quote.mutate()} disabled={!pair || quote.isPending}>Quote</Button>
            <Button disabled={!result?.best || me?.mode !== "auto_execute"} onClick={() => execute.mutate()}>Execute</Button>
          </div>
        </CardContent>
      </Card>
      <Card className="col-span-12 lg:col-span-8">
        <CardHeader className="space-y-1">
          <CardTitle>Venues</CardTitle>
          <CardDescription>
            One row per connected exchange. <code>Expected</code> is the volume-weighted fill price walking
            the book, <code>Spread</code> is top-of-book in bps, <code>Slippage</code> is the cost of crossing
            the book, <code>Cost</code> is fee + spread + slippage in USDT. The highlighted row is the winner.
          </CardDescription>
        </CardHeader>
        <CardContent>{result ? <RouteTable result={result} /> : <Empty />}</CardContent>
      </Card>
    </div>
  );
}

function Optimizer() {
  const watchlist = useQuery<WatchlistEntry[]>({ queryKey: ["watchlist"], queryFn: getWatchlist });
  const strategies = useQuery<StrategyListItem[]>({ queryKey: ["strategies"], queryFn: async () => (await api.get("/strategies")).data });
  const [pair, setPair] = useFirstPair(watchlist.data ?? []);
  const [strategyId, setStrategyId] = useState("");
  const [grid, setGrid] = useState('{"rsi_overbought":[65,70,75]}');
  const [result, setResult] = useState<OptimizerResult | null>(null);
  useEffect(() => {
    if (!strategyId && strategies.data?.[0]) setStrategyId(String(strategies.data[0].id));
  }, [strategies.data, strategyId]);
  const run = useMutation({
    mutationFn: async () => {
      const [exchange, symbol] = pair.split(":");
      return (await api.post<OptimizerResult>(`/strategies/${strategyId}/optimize`, {
        exchange,
        symbol,
        param_grid: JSON.parse(grid || "{}"),
        train_hours: 168,
        validation_hours: 72,
        notional_usdt: 100,
      })).data;
    },
    onSuccess: setResult,
    onError: errToast,
  });
  return (
    <div className="grid grid-cols-12 gap-4">
      <ToolIntro kind="optimizer" />
      <Card className="col-span-12 lg:col-span-4">
        <CardHeader className="space-y-1">
          <CardTitle>Search</CardTitle>
          <CardDescription>
            Pair + strategy + a JSON grid of params to sweep. Each combo is backtested on a 168h
            train+validation window and re-tested on the last 72h as validation. Up to 64 combos per run.
            Example: <code>{'{"rsi_overbought":[65,70,75]}'}</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <PairSelect value={pair} onChange={setPair} watchlist={watchlist.data ?? []} />
          <Select value={strategyId} onValueChange={setStrategyId}>
            <SelectTrigger><SelectValue placeholder="Strategy" /></SelectTrigger>
            <SelectContent>{strategies.data?.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}</SelectContent>
          </Select>
          <Label>Param grid JSON</Label>
          <textarea className="min-h-24 rounded-md border border-input bg-transparent p-2 font-mono text-xs" value={grid} onChange={(e) => setGrid(e.target.value)} />
          <Button disabled={!pair || !strategyId || run.isPending} onClick={() => run.mutate()}>
            <Play className="mr-1 h-4 w-4" />{run.isPending ? "Running..." : "Run"}
          </Button>
        </CardContent>
      </Card>
      <Card className="col-span-12 lg:col-span-8">
        <CardHeader className="space-y-1">
          <CardTitle>Ranked Parameters</CardTitle>
          <CardDescription>
            Sorted by composite score = validation PnL + 0.25·win-rate + 0.25·stability − 0.75·drawdown.
            <code> Stability</code> measures how close train and validation PnL are — high stability means
            the params didn't overfit. Pick the top robust row, not just the top PnL row.
          </CardDescription>
        </CardHeader>
        <CardContent>{result ? <OptimizerTable result={result} /> : <Empty />}</CardContent>
      </Card>
    </div>
  );
}

function Scenarios() {
  const [preset, setPreset] = useState("gap_down");
  const [magnitude, setMagnitude] = useState(5);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const run = useMutation({
    mutationFn: async () => (await api.post<ScenarioResult>("/risk/scenarios", { preset, magnitude_pct: magnitude })).data,
    onSuccess: setResult,
    onError: errToast,
  });
  return (
    <div className="grid grid-cols-12 gap-4">
      <ToolIntro kind="scenarios" />
      <Card className="col-span-12 lg:col-span-4">
        <CardHeader className="space-y-1">
          <CardTitle>Shock</CardTitle>
          <CardDescription>
            Choose a preset and a magnitude in percent. Shocks are applied uniformly to every open
            position; longs lose on a gap_down, shorts gain. <code>volatility_cascade</code> is 1.5× the
            given magnitude. Read-only — nothing is sent to the exchange.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Select value={preset} onValueChange={setPreset}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="gap_down">Gap down</SelectItem>
              <SelectItem value="gap_up">Gap up</SelectItem>
              <SelectItem value="volatility_cascade">Volatility cascade</SelectItem>
              <SelectItem value="stop_series">Stop series</SelectItem>
              <SelectItem value="correlation_spike">Correlation spike</SelectItem>
            </SelectContent>
          </Select>
          <NumberField label="Magnitude %" value={magnitude} onChange={setMagnitude} />
          <Button onClick={() => run.mutate()} disabled={run.isPending}>Simulate</Button>
        </CardContent>
      </Card>
      <Card className="col-span-12 lg:col-span-8">
        <CardHeader className="space-y-1">
          <CardTitle>Impact</CardTitle>
          <CardDescription>
            <code>PnL</code> is the sum of per-position shocked losses. <code>Daily</code> adds today's
            already-realized PnL on top. <code>Limit Used</code> is the share of your daily loss limit
            consumed by the projected daily PnL; <code>Status</code> turns <strong>BREACH</strong> if it
            would trip the kill-switch.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {result ? (
            <>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Stat label="PnL" value={`$${result.total_pnl_usdt.toFixed(2)}`} className={result.total_pnl_usdt >= 0 ? "text-success" : "text-destructive"} />
                <Stat label="Daily" value={`$${result.projected_daily_pnl_usdt.toFixed(2)}`} />
                <Stat label="Limit Used" value={`${(result.daily_loss_usage * 100).toFixed(0)}%`} />
                <Stat label="Status" value={result.daily_loss_breached ? "BREACH" : "OK"} className={result.daily_loss_breached ? "text-destructive" : "text-success"} />
              </div>
              <ScenarioTable result={result} />
            </>
          ) : <Empty />}
        </CardContent>
      </Card>
    </div>
  );
}

function IntentTable({ intents }: { intents: RebalancePlan["intents"] }) {
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Pair</TableHead><TableHead>Side</TableHead><TableHead className="text-right">Notional</TableHead><TableHead>Reason</TableHead></TableRow></TableHeader>
      <TableBody>{intents.map((i, idx) => (
        <TableRow key={idx}><TableCell><PairBadge exchange={i.exchange} symbol={i.symbol} /></TableCell><TableCell><Badge variant={i.side === "buy" ? "success" : "destructive"}>{i.side}</Badge></TableCell><TableCell className="num text-right">${i.notional_usdt.toFixed(2)}</TableCell><TableCell className="text-xs text-muted-foreground">{i.reason}</TableCell></TableRow>
      ))}</TableBody>
    </Table>
  );
}

function RouteTable({ result }: { result: RouteResult }) {
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Venue</TableHead><TableHead className="text-right">Expected</TableHead><TableHead className="text-right">Spread</TableHead><TableHead className="text-right">Slippage</TableHead><TableHead className="text-right">Cost</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
      <TableBody>{result.candidates.map((c) => (
        <TableRow key={c.exchange} className={cn(result.best?.exchange === c.exchange && "bg-primary/5")}>
          <TableCell className="font-mono uppercase">{c.exchange}</TableCell>
          <TableCell className="num text-right">{c.expected_price?.toFixed(2) ?? "-"}</TableCell>
          <TableCell className="num text-right">{c.spread_bps?.toFixed(2) ?? "-"}</TableCell>
          <TableCell className="num text-right">{c.slippage_bps?.toFixed(2) ?? "-"}</TableCell>
          <TableCell className="num text-right">{c.total_cost_usdt?.toFixed(4) ?? "-"}</TableCell>
          <TableCell><Badge variant={c.ok ? "success" : "destructive"}>{c.ok ? "OK" : c.reason}</Badge></TableCell>
        </TableRow>
      ))}</TableBody>
    </Table>
  );
}

function OptimizerTable({ result }: { result: OptimizerResult }) {
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Params</TableHead><TableHead className="text-right">Score</TableHead><TableHead className="text-right">Val PnL</TableHead><TableHead className="text-right">Win</TableHead><TableHead className="text-right">DD</TableHead><TableHead className="text-right">Stability</TableHead></TableRow></TableHeader>
      <TableBody>{result.candidates.map((c, i) => (
        <TableRow key={i}><TableCell className="font-mono text-xs">{JSON.stringify(c.params)}</TableCell><TableCell className="num text-right">{c.score.toFixed(3)}</TableCell><TableCell className="num text-right">{(c.validation.total_pnl_pct * 100).toFixed(1)}%</TableCell><TableCell className="num text-right">{(c.validation.win_rate * 100).toFixed(0)}%</TableCell><TableCell className="num text-right">{(c.validation.max_drawdown_pct * 100).toFixed(1)}%</TableCell><TableCell className="num text-right">{(c.stability * 100).toFixed(0)}%</TableCell></TableRow>
      ))}</TableBody>
    </Table>
  );
}

function ScenarioTable({ result }: { result: ScenarioResult }) {
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Symbol</TableHead><TableHead>Side</TableHead><TableHead className="text-right">Shock</TableHead><TableHead className="text-right">Notional</TableHead><TableHead className="text-right">PnL</TableHead></TableRow></TableHeader>
      <TableBody>{result.positions.map((p, i) => (
        <TableRow key={i}><TableCell className="font-mono">{p.symbol}</TableCell><TableCell>{p.side}</TableCell><TableCell className="num text-right">{(p.shock_pct * 100).toFixed(1)}%</TableCell><TableCell className="num text-right">${p.notional_usdt.toFixed(2)}</TableCell><TableCell className={cn("num text-right", p.pnl_usdt >= 0 ? "text-success" : "text-destructive")}>${p.pnl_usdt.toFixed(2)}</TableCell></TableRow>
      ))}</TableBody>
    </Table>
  );
}

function PairSelect({ value, onChange, watchlist }: { value: string; onChange: (v: string) => void; watchlist: WatchlistEntry[] }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger><SelectValue placeholder="Pair" /></SelectTrigger>
      <SelectContent>{watchlist.map((p) => <SelectItem key={`${p.exchange}:${p.symbol}`} value={`${p.exchange}:${p.symbol}`}>{p.exchange.toUpperCase()} · {p.symbol}</SelectItem>)}</SelectContent>
    </Select>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return <div className="flex flex-col gap-1"><Label>{label}</Label><Input className="num" type="number" value={value} onChange={(e) => onChange(Number(e.target.value) || 0)} /></div>;
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return <div className="flex flex-col gap-1"><Label>{label}</Label><Input className="num" type="number" value={value} onChange={(e) => onChange(e.target.value)} /></div>;
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return <div className="rounded-md border border-border p-3"><div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">{label}</div><div className={cn("num text-lg font-semibold", className)}>{value}</div></div>;
}

function Empty() {
  return <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No result yet.</div>;
}

function useFirstPair(watchlist: WatchlistEntry[]): [string, (v: string) => void] {
  const [pair, setPair] = useState("");
  const first = useMemo(() => watchlist[0] ? `${watchlist[0].exchange}:${watchlist[0].symbol}` : "", [watchlist]);
  useEffect(() => {
    if (!pair && first) setPair(first);
  }, [first, pair]);
  return [pair, setPair];
}

function errToast(e: any) {
  toast.error(e?.response?.data?.detail || e?.message || "request failed");
}
