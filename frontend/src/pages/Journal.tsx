import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  Filter,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { createChart, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import {
  AIEvaluation,
  AISettings,
  DealRow,
  EquityPoint,
  JournalFilterOptions,
  JournalFilters,
  JournalQueryParams,
  JournalStats,
  evaluateDeal,
  getAISettings,
  getDealEvaluations,
  getJournalDeals,
  getJournalEquityCurve,
  getJournalFilterOptions,
  getJournalStats,
  updateDealAnnotations,
} from "@/api/client";
import PairBadge from "@/components/PairBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useChartTheme } from "@/lib/useChartTheme";
import { cn } from "@/lib/utils";

type FilterState = {
  date_from: string;
  date_to: string;
  symbols: string[];
  exchange: string;
  side: "all" | "buy" | "sell";
  status: "all" | "open" | "closed" | "partial";
  strategy_id: string;
  outcome: "all" | "win" | "loss" | "breakeven";
  search: string;
};

const DEFAULT_FILTERS: FilterState = {
  date_from: "",
  date_to: "",
  symbols: [],
  exchange: "all",
  side: "all",
  status: "all",
  strategy_id: "all",
  outcome: "all",
  search: "",
};

type SortField = NonNullable<JournalQueryParams["sort"]>;
type SortOrder = NonNullable<JournalQueryParams["order"]>;

function toApiFilters(f: FilterState): JournalFilters {
  const out: JournalFilters = {};
  if (f.date_from) out.date_from = new Date(f.date_from).toISOString();
  if (f.date_to) {
    const d = new Date(f.date_to);
    d.setHours(23, 59, 59, 999);
    out.date_to = d.toISOString();
  }
  if (f.symbols.length) out.symbols = f.symbols;
  if (f.exchange !== "all") out.exchange = f.exchange;
  if (f.side !== "all") out.side = f.side;
  if (f.status !== "all") out.status = f.status;
  if (f.strategy_id !== "all") out.strategy_id = Number(f.strategy_id);
  if (f.outcome !== "all") out.outcome = f.outcome;
  if (f.search.trim()) out.search = f.search.trim();
  return out;
}

function fmtUsd(n: number | null | undefined, opts: { signed?: boolean } = {}): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = opts.signed && n > 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}

function fmtPct(n: number | null | undefined, opts: { signed?: boolean } = {}): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = opts.signed && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtDuration(s: number | null): string {
  if (s === null || s === undefined) return "—";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

const COLUMNS: { key: string; label: string; sort?: SortField; align?: "left" | "right" }[] = [
  { key: "when", label: "When", sort: "created_at" },
  { key: "closed", label: "Closed", sort: "closed_at" },
  { key: "pair", label: "Pair" },
  { key: "strategy", label: "Strategy" },
  { key: "side", label: "Side" },
  { key: "qty", label: "Qty", align: "right" },
  { key: "entry", label: "Entry", align: "right" },
  { key: "exit", label: "Exit", align: "right" },
  { key: "notional", label: "Notional", align: "right" },
  { key: "pnl", label: "PnL $", sort: "pnl", align: "right" },
  { key: "roi", label: "ROI %", sort: "roi", align: "right" },
  { key: "r", label: "R", align: "right" },
  { key: "duration", label: "Duration", sort: "duration", align: "right" },
  { key: "status", label: "Status" },
  { key: "tags", label: "Tags" },
];

export default function Journal() {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortField>("created_at");
  const [order, setOrder] = useState<SortOrder>("desc");
  const [openDeal, setOpenDeal] = useState<DealRow | null>(null);

  const apiFilters = useMemo(() => toApiFilters(filters), [filters]);

  const options = useQuery<JournalFilterOptions>({
    queryKey: ["journal", "filter-options"],
    queryFn: getJournalFilterOptions,
  });

  const deals = useQuery<DealRow[]>({
    queryKey: ["journal", "deals", apiFilters, sort, order],
    queryFn: () =>
      getJournalDeals({ ...apiFilters, sort, order, limit: 500, offset: 0 }),
    placeholderData: (prev) => prev,
  });

  const stats = useQuery<JournalStats>({
    queryKey: ["journal", "stats", apiFilters],
    queryFn: () => getJournalStats(apiFilters),
    placeholderData: (prev) => prev,
  });

  const equity = useQuery<{ points: EquityPoint[] }>({
    queryKey: ["journal", "equity", apiFilters],
    queryFn: () => getJournalEquityCurve(apiFilters),
    placeholderData: (prev) => prev,
  });

  const toggleSort = (field: SortField) => {
    if (sort === field) {
      setOrder(order === "asc" ? "desc" : "asc");
    } else {
      setSort(field);
      setOrder("desc");
    }
  };

  const reset = () => {
    setFilters(DEFAULT_FILTERS);
    setSort("created_at");
    setOrder("desc");
  };

  const activeFilterCount =
    (filters.date_from ? 1 : 0) +
    (filters.date_to ? 1 : 0) +
    filters.symbols.length +
    (filters.exchange !== "all" ? 1 : 0) +
    (filters.side !== "all" ? 1 : 0) +
    (filters.status !== "all" ? 1 : 0) +
    (filters.strategy_id !== "all" ? 1 : 0) +
    (filters.outcome !== "all" ? 1 : 0) +
    (filters.search ? 1 : 0);

  return (
    <div className="flex flex-col gap-3 max-w-[1400px]">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-mono uppercase tracking-wider">Trading Journal</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Filter, color-code and annotate every closed deal across exchanges.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="muted" className="gap-1">
            <Filter className="h-3 w-3" />
            {activeFilterCount} filter{activeFilterCount === 1 ? "" : "s"}
          </Badge>
          <Button variant="ghost" size="sm" onClick={reset} className="gap-1">
            <RotateCcw className="h-3 w-3" />
            Reset
          </Button>
        </div>
      </div>

      <FilterBar
        filters={filters}
        setFilters={setFilters}
        options={options.data ?? null}
      />

      <KPIStrip stats={stats.data ?? null} />

      <EquityCard points={equity.data?.points ?? []} />

      <div className="grid gap-3 lg:grid-cols-2">
        <DistributionCard deals={deals.data ?? []} />
        <BySymbolCard buckets={stats.data?.by_symbol ?? {}} />
      </div>

      <DealsTable
        deals={deals.data ?? []}
        loading={deals.isLoading}
        sort={sort}
        order={order}
        toggleSort={toggleSort}
        onOpen={setOpenDeal}
      />

      <DealDialog
        deal={openDeal}
        onClose={() => setOpenDeal(null)}
      />
    </div>
  );
}

// ---------- Filter bar ----------

function FilterBar({
  filters,
  setFilters,
  options,
}: {
  filters: FilterState;
  setFilters: React.Dispatch<React.SetStateAction<FilterState>>;
  options: JournalFilterOptions | null;
}) {
  const set = (k: keyof FilterState, v: FilterState[keyof FilterState]) =>
    setFilters((f) => ({ ...f, [k]: v }) as FilterState);

  const toggleSymbol = (s: string) => {
    setFilters((f) => {
      const next = f.symbols.includes(s)
        ? f.symbols.filter((x) => x !== s)
        : [...f.symbols, s];
      return { ...f, symbols: next };
    });
  };

  return (
    <Card>
      <CardContent className="p-3">
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
          <FilterField label="From">
            <Input
              type="date"
              value={filters.date_from}
              onChange={(e) => set("date_from", e.target.value)}
            />
          </FilterField>
          <FilterField label="To">
            <Input
              type="date"
              value={filters.date_to}
              onChange={(e) => set("date_to", e.target.value)}
            />
          </FilterField>
          <FilterField label="Symbols">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 w-full justify-between font-normal"
                >
                  <span className="truncate text-sm">
                    {filters.symbols.length === 0
                      ? "All"
                      : `${filters.symbols.length} selected`}
                  </span>
                  <ChevronDown className="h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="max-h-72 overflow-auto">
                <DropdownMenuLabel>Symbols</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {(options?.symbols ?? []).length === 0 && (
                  <div className="px-2 py-1 text-xs text-muted-foreground">
                    No traded symbols yet.
                  </div>
                )}
                {(options?.symbols ?? []).map((s) => (
                  <DropdownMenuCheckboxItem
                    key={s}
                    checked={filters.symbols.includes(s)}
                    onCheckedChange={() => toggleSymbol(s)}
                    onSelect={(e) => e.preventDefault()}
                  >
                    {s}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </FilterField>
          <FilterField label="Exchange">
            <Select
              value={filters.exchange}
              onValueChange={(v) => set("exchange", v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                {(options?.exchanges ?? []).map((e) => (
                  <SelectItem key={e} value={e}>
                    {e}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField label="Side">
            <Select
              value={filters.side}
              onValueChange={(v) => set("side", v as FilterState["side"])}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="buy">Long (buy)</SelectItem>
                <SelectItem value="sell">Short (sell)</SelectItem>
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField label="Outcome">
            <Select
              value={filters.outcome}
              onValueChange={(v) => set("outcome", v as FilterState["outcome"])}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="win">Wins</SelectItem>
                <SelectItem value="loss">Losses</SelectItem>
                <SelectItem value="breakeven">Break-even</SelectItem>
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField label="Status">
            <Select
              value={filters.status}
              onValueChange={(v) => set("status", v as FilterState["status"])}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="partial">Partial</SelectItem>
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField label="Strategy">
            <Select
              value={filters.strategy_id}
              onValueChange={(v) => set("strategy_id", v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                {(options?.strategies ?? []).map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
          <FilterField label="Search" className="md:col-span-3 lg:col-span-4 xl:col-span-2">
            <Input
              placeholder="Symbol or notes…"
              value={filters.search}
              onChange={(e) => set("search", e.target.value)}
            />
          </FilterField>
        </div>
        {filters.symbols.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {filters.symbols.map((s) => (
              <button
                key={s}
                onClick={() => toggleSymbol(s)}
                className="inline-flex items-center gap-1 rounded-sm border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:bg-muted/80"
              >
                {s}
                <X className="h-3 w-3" />
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FilterField({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {children}
    </div>
  );
}

// ---------- KPI strip ----------

function KPIStrip({ stats }: { stats: JournalStats | null }) {
  const netColor =
    stats && stats.net_pnl > 0
      ? "text-success"
      : stats && stats.net_pnl < 0
        ? "text-destructive"
        : "";
  const wrColor =
    stats && stats.win_rate >= 0.5 ? "text-success" : "text-destructive";

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
      <Stat
        label="Net PnL"
        value={fmtUsd(stats?.net_pnl ?? null, { signed: true })}
        className={netColor}
      />
      <Stat
        label="Win Rate"
        value={
          stats ? `${(stats.win_rate * 100).toFixed(0)}%` : "—"
        }
        sub={stats ? `${stats.wins}W · ${stats.losses}L` : undefined}
        className={stats ? wrColor : ""}
      />
      <Stat
        label="Profit Factor"
        value={
          stats?.profit_factor === null || stats?.profit_factor === undefined
            ? "∞"
            : stats.profit_factor.toFixed(2)
        }
      />
      <Stat
        label="Expectancy"
        value={fmtUsd(stats?.expectancy ?? null, { signed: true })}
      />
      <Stat
        label="Avg Win"
        value={fmtUsd(stats?.avg_win ?? null)}
        className="text-success"
      />
      <Stat
        label="Avg Loss"
        value={fmtUsd(stats?.avg_loss ?? null)}
        className="text-destructive"
      />
      <Stat
        label="Max DD"
        value={fmtUsd(stats ? -stats.max_drawdown_usdt : null)}
        sub={stats ? fmtPct(-stats.max_drawdown_pct) : undefined}
        className="text-destructive"
      />
      <Stat
        label="Trades"
        value={stats ? String(stats.count) : "—"}
        sub={stats && stats.open ? `${stats.open} open` : undefined}
      />
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  className = "",
}: {
  label: string;
  value: string;
  sub?: string;
  className?: string;
}) {
  return (
    <Card>
      <CardContent className="p-3">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className={cn("text-lg num font-semibold", className)}>{value}</div>
        {sub && (
          <div className="text-xs text-muted-foreground num">{sub}</div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------- Equity curve ----------

function EquityCard({ points }: { points: EquityPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const theme = useChartTheme();

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: theme.background }, textColor: theme.muted },
      grid: {
        vertLines: { color: theme.border },
        horzLines: { color: theme.border },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: theme.border,
      },
      rightPriceScale: { borderColor: theme.border },
    });
    const s = chart.addAreaSeries({
      lineColor: theme.primary,
      topColor: theme.primary,
      bottomColor: "transparent",
      lineWidth: 2,
      priceLineVisible: false,
    });
    chartRef.current = chart;
    seriesRef.current = s;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    chart.applyOptions({
      layout: { background: { color: theme.background }, textColor: theme.muted },
      grid: {
        vertLines: { color: theme.border },
        horzLines: { color: theme.border },
      },
      timeScale: { borderColor: theme.border },
      rightPriceScale: { borderColor: theme.border },
    });
    series.applyOptions({
      lineColor: theme.primary,
      topColor: theme.primary,
    });
  }, [theme]);

  useEffect(() => {
    if (!seriesRef.current) return;
    const data = points
      .map((p) => ({
        time: (Math.floor(new Date(p.t).getTime() / 1000) as unknown) as Time,
        value: p.equity,
      }))
      // lightweight-charts requires strictly increasing timestamps; collapse
      // duplicates by keeping the later equity value at that second.
      .reduce((acc: { time: Time; value: number }[], cur) => {
        if (acc.length && acc[acc.length - 1].time === cur.time) {
          acc[acc.length - 1] = cur;
        } else {
          acc.push(cur);
        }
        return acc;
      }, []);
    seriesRef.current.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [points]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="font-mono uppercase tracking-wider">
          Equity curve
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div ref={ref} className="h-56 w-full bg-card" />
        {points.length === 0 && (
          <div className="border-t border-border p-3 text-center text-xs text-muted-foreground">
            No closed deals in the selected range.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------- PnL distribution ----------

function DistributionCard({ deals }: { deals: DealRow[] }) {
  const closed = deals.filter((d) => d.status === "closed");
  const pnls = closed.map((d) => d.realized_pnl_usdt);

  if (pnls.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="font-mono uppercase tracking-wider">
            PnL distribution
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6 text-center text-xs text-muted-foreground">
          No closed deals.
        </CardContent>
      </Card>
    );
  }

  const min = Math.min(...pnls);
  const max = Math.max(...pnls);
  // Build bins symmetric around zero where possible.
  const bound = Math.max(Math.abs(min), Math.abs(max)) || 1;
  const BINS = 14;
  const step = (bound * 2) / BINS;
  const buckets = Array(BINS)
    .fill(0)
    .map((_, i) => {
      const lo = -bound + i * step;
      const hi = lo + step;
      return { lo, hi, count: 0 };
    });
  for (const v of pnls) {
    const i = Math.min(BINS - 1, Math.max(0, Math.floor((v + bound) / step)));
    buckets[i].count++;
  }
  const maxCount = Math.max(...buckets.map((b) => b.count), 1);

  const W = 520;
  const H = 160;
  const barW = W / BINS;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="font-mono uppercase tracking-wider">
          PnL distribution
        </CardTitle>
      </CardHeader>
      <CardContent>
        <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full">
          {buckets.map((b, i) => {
            const h = (b.count / maxCount) * (H - 24);
            const isNeg = b.hi <= 0;
            return (
              <g key={i}>
                <rect
                  x={i * barW + 1}
                  y={H - h - 16}
                  width={barW - 2}
                  height={h}
                  className={isNeg ? "fill-destructive/70" : "fill-success/70"}
                />
                {b.count > 0 && (
                  <text
                    x={i * barW + barW / 2}
                    y={H - h - 18}
                    textAnchor="middle"
                    className="fill-muted-foreground text-[8px]"
                  >
                    {b.count}
                  </text>
                )}
              </g>
            );
          })}
          <line
            x1={W / 2}
            x2={W / 2}
            y1={0}
            y2={H - 16}
            className="stroke-border"
            strokeDasharray="2 3"
          />
          <text
            x={2}
            y={H - 4}
            className="fill-muted-foreground text-[8px] font-mono uppercase"
          >
            {fmtUsd(-bound, { signed: true })}
          </text>
          <text
            x={W - 2}
            y={H - 4}
            textAnchor="end"
            className="fill-muted-foreground text-[8px] font-mono uppercase"
          >
            {fmtUsd(bound, { signed: true })}
          </text>
        </svg>
      </CardContent>
    </Card>
  );
}

// ---------- PnL by symbol ----------

function BySymbolCard({
  buckets,
}: {
  buckets: Record<string, { count: number; net_pnl: number; win_rate: number }>;
}) {
  const entries = Object.entries(buckets);
  if (entries.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="font-mono uppercase tracking-wider">
            PnL by symbol
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6 text-center text-xs text-muted-foreground">
          No closed deals.
        </CardContent>
      </Card>
    );
  }
  const sorted = entries
    .slice()
    .sort((a, b) => Math.abs(b[1].net_pnl) - Math.abs(a[1].net_pnl))
    .slice(0, 10);
  const maxAbs = Math.max(...sorted.map(([, v]) => Math.abs(v.net_pnl)), 1);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="font-mono uppercase tracking-wider">
          PnL by symbol
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-1">
          {sorted.map(([sym, v]) => {
            const pct = (Math.abs(v.net_pnl) / maxAbs) * 100;
            const pos = v.net_pnl >= 0;
            return (
              <div key={sym} className="flex items-center gap-2 text-xs">
                <span className="w-24 truncate font-mono">{sym}</span>
                <div className="relative h-4 flex-1 overflow-hidden rounded-sm bg-muted/40">
                  <div
                    className={cn(
                      "absolute inset-y-0",
                      pos
                        ? "left-1/2 bg-success/70"
                        : "right-1/2 bg-destructive/70",
                    )}
                    style={{ width: `${pct / 2}%` }}
                  />
                  <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
                </div>
                <span
                  className={cn(
                    "num w-20 text-right tabular-nums",
                    pos ? "text-success" : "text-destructive",
                  )}
                >
                  {fmtUsd(v.net_pnl, { signed: true })}
                </span>
                <span className="w-10 text-right text-muted-foreground num">
                  {v.count}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------- Deals table ----------

function DealsTable({
  deals,
  loading,
  sort,
  order,
  toggleSort,
  onOpen,
}: {
  deals: DealRow[];
  loading: boolean;
  sort: SortField;
  order: SortOrder;
  toggleSort: (f: SortField) => void;
  onOpen: (d: DealRow) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="font-mono uppercase tracking-wider">
          Deals
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            {deals.length} row{deals.length === 1 ? "" : "s"}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {COLUMNS.map((c) => {
                  const active = c.sort === sort;
                  const Icon = active
                    ? order === "asc"
                      ? ArrowUp
                      : ArrowDown
                    : ArrowUpDown;
                  return (
                    <TableHead
                      key={c.key}
                      className={cn(
                        c.align === "right" && "text-right",
                        c.sort && "cursor-pointer select-none hover:text-foreground",
                      )}
                      onClick={() => c.sort && toggleSort(c.sort)}
                    >
                      <span className="inline-flex items-center gap-1">
                        {c.label}
                        {c.sort && (
                          <Icon
                            className={cn(
                              "h-3 w-3",
                              active ? "opacity-100" : "opacity-30",
                            )}
                          />
                        )}
                      </span>
                    </TableHead>
                  );
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && deals.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={COLUMNS.length}
                    className="p-6 text-center text-sm text-muted-foreground"
                  >
                    Loading…
                  </TableCell>
                </TableRow>
              )}
              {!loading && deals.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={COLUMNS.length}
                    className="p-6 text-center text-sm text-muted-foreground"
                  >
                    No deals match the current filters.
                  </TableCell>
                </TableRow>
              )}
              {deals.map((d) => {
                const closed = d.status === "closed";
                const win = closed && d.realized_pnl_usdt > 0;
                const loss = closed && d.realized_pnl_usdt < 0;
                const rowTint = win
                  ? "bg-success/5 hover:bg-success/10"
                  : loss
                    ? "bg-destructive/5 hover:bg-destructive/10"
                    : "";
                const pnlColor = win
                  ? "text-success"
                  : loss
                    ? "text-destructive"
                    : "text-muted-foreground";
                return (
                  <TableRow
                    key={d.id}
                    className={cn("cursor-pointer", rowTint)}
                    onClick={() => onOpen(d)}
                  >
                    <TableCell className="text-xs num text-muted-foreground">
                      {fmtDateTime(d.created_at)}
                    </TableCell>
                    <TableCell className="text-xs num text-muted-foreground">
                      {fmtDateTime(d.closed_at)}
                    </TableCell>
                    <TableCell>
                      <PairBadge exchange={d.exchange} symbol={d.symbol} />
                    </TableCell>
                    <TableCell className="text-xs">
                      {d.strategy_name || (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={d.side === "buy" ? "success" : "destructive"}
                      >
                        {d.side === "buy" ? "LONG" : "SHORT"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right num">
                      {fmtNum(d.qty, 6)}
                    </TableCell>
                    <TableCell className="text-right num">
                      {fmtNum(d.entry_price)}
                    </TableCell>
                    <TableCell className="text-right num">
                      {fmtNum(d.exit_price)}
                    </TableCell>
                    <TableCell className="text-right num">
                      ${fmtNum(d.notional_usdt)}
                    </TableCell>
                    <TableCell
                      className={cn("text-right num font-semibold", pnlColor)}
                    >
                      {closed ? fmtUsd(d.realized_pnl_usdt, { signed: true }) : "—"}
                    </TableCell>
                    <TableCell className={cn("text-right num", pnlColor)}>
                      {closed ? fmtPct(d.roi_pct, { signed: true }) : "—"}
                    </TableCell>
                    <TableCell className="text-right num">
                      {d.r_multiple !== null
                        ? `${d.r_multiple > 0 ? "+" : ""}${d.r_multiple.toFixed(2)}R`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right num text-muted-foreground">
                      {fmtDuration(d.duration_s)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="muted">{d.status}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {d.tags.length === 0 ? (
                          <span className="text-muted-foreground text-xs">
                            —
                          </span>
                        ) : (
                          d.tags.slice(0, 4).map((t) => (
                            <Badge key={t} variant="outline">
                              {t}
                            </Badge>
                          ))
                        )}
                        {d.tags.length > 4 && (
                          <span className="text-muted-foreground text-xs">
                            +{d.tags.length - 4}
                          </span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------- Deal dialog ----------

function DealDialog({
  deal,
  onClose,
}: {
  deal: DealRow | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  useEffect(() => {
    if (deal) {
      setNotes(deal.notes ?? "");
      setTags(deal.tags ?? []);
      setTagInput("");
    }
  }, [deal]);

  const save = useMutation({
    mutationFn: (payload: { notes: string; tags: string[] }) => {
      if (!deal) return Promise.reject(new Error("no deal"));
      return updateDealAnnotations(deal.id, payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal", "deals"] });
      onClose();
    },
  });

  const addTag = () => {
    const t = tagInput.trim();
    if (!t) return;
    if (tags.includes(t)) {
      setTagInput("");
      return;
    }
    setTags([...tags, t]);
    setTagInput("");
  };

  if (!deal) return null;

  const closed = deal.status === "closed";
  const pnlColor =
    closed && deal.realized_pnl_usdt > 0
      ? "text-success"
      : closed && deal.realized_pnl_usdt < 0
        ? "text-destructive"
        : "";

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-mono uppercase tracking-wider">
            <PairBadge exchange={deal.exchange} symbol={deal.symbol} />
            <Badge variant={deal.side === "buy" ? "success" : "destructive"}>
              {deal.side === "buy" ? "LONG" : "SHORT"}
            </Badge>
            <span className={cn("text-base", pnlColor)}>
              {closed ? fmtUsd(deal.realized_pnl_usdt, { signed: true }) : "OPEN"}
            </span>
          </DialogTitle>
          <DialogDescription>
            Deal #{deal.id} · opened {fmtDateTime(deal.created_at)}
            {deal.closed_at && ` · closed ${fmtDateTime(deal.closed_at)}`}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm md:grid-cols-3">
          <DetailField label="Qty" value={fmtNum(deal.qty, 6)} />
          <DetailField label="Notional" value={`$${fmtNum(deal.notional_usdt)}`} />
          <DetailField label="Entry" value={fmtNum(deal.entry_price)} />
          <DetailField label="Exit" value={fmtNum(deal.exit_price)} />
          <DetailField label="SL" value={deal.sl !== null ? fmtNum(deal.sl) : "—"} />
          <DetailField label="TP" value={deal.tp !== null ? fmtNum(deal.tp) : "—"} />
          <DetailField
            label="PnL"
            value={closed ? fmtUsd(deal.realized_pnl_usdt, { signed: true }) : "—"}
            className={pnlColor}
          />
          <DetailField
            label="ROI"
            value={closed ? fmtPct(deal.roi_pct, { signed: true }) : "—"}
            className={pnlColor}
          />
          <DetailField
            label="R"
            value={
              deal.r_multiple !== null
                ? `${deal.r_multiple > 0 ? "+" : ""}${deal.r_multiple.toFixed(2)}R`
                : "—"
            }
            className={pnlColor}
          />
          <DetailField label="Duration" value={fmtDuration(deal.duration_s)} />
          <DetailField label="Fees" value={fmtUsd(deal.fee_usdt)} />
          <DetailField
            label="Strategy"
            value={deal.strategy_name ?? "—"}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            Notes
          </label>
          <Textarea
            rows={4}
            placeholder="What was the setup? Did the plan work? What would you do differently?"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            Tags
          </label>
          <div className="flex flex-wrap gap-1">
            {tags.map((t) => (
              <button
                key={t}
                onClick={() => setTags(tags.filter((x) => x !== t))}
                className="inline-flex items-center gap-1 rounded-sm border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider hover:bg-muted/80"
              >
                {t}
                <X className="h-3 w-3" />
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="breakout, fomo, news-driven…"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addTag();
                }
              }}
            />
            <Button variant="outline" onClick={addTag} disabled={!tagInput.trim()}>
              Add
            </Button>
          </div>
        </div>

        <AIReviewSection dealId={deal.id} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => save.mutate({ notes, tags })}
            disabled={save.isPending}
          >
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AIReviewSection({ dealId }: { dealId: number }) {
  const cfg = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: getAISettings,
  });
  const existing = useQuery({
    queryKey: ["ai-evaluations", dealId],
    queryFn: () => getDealEvaluations(dealId),
  });

  const qc = useQueryClient();
  const runEval = useMutation({
    mutationFn: () => evaluateDeal(dealId),
    onSuccess: (data) => {
      qc.setQueryData(["ai-evaluations", dealId], data);
    },
  });

  const hasKey = cfg.data?.has_key === true;
  const evaluations = runEval.data?.evaluations ?? existing.data?.evaluations ?? [];
  const hasResults = evaluations.length > 0;

  let errorText: string | null = null;
  if (runEval.isError) {
    const err = runEval.error as any;
    errorText = err?.response?.data?.detail || "Evaluation failed";
  }

  return (
    <div className="flex flex-col gap-2 border-t border-border pt-4">
      <div className="flex items-center justify-between">
        <label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <Sparkles className="h-3 w-3" />
          AI Review
        </label>
        {hasKey && (
          <Button
            size="sm"
            variant={hasResults ? "outline" : "default"}
            onClick={() => runEval.mutate()}
            disabled={runEval.isPending}
          >
            <Sparkles className="h-3 w-3" />
            {runEval.isPending
              ? "Evaluating…"
              : hasResults
                ? "Re-evaluate"
                : "Evaluate with AI (3 models)"}
          </Button>
        )}
      </div>

      {!cfg.isLoading && !hasKey && (
        <div className="rounded-md border border-dashed border-border bg-muted/30 p-3 text-xs text-muted-foreground">
          Add an OpenRouter API key in{" "}
          <span className="font-medium">Settings → AI Evaluation</span> to
          enable per-deal AI reviews from three models in parallel.
        </div>
      )}

      {errorText && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
          {errorText}
        </div>
      )}

      {runEval.isPending && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="rounded-md border border-border p-3 text-xs text-muted-foreground animate-pulse"
            >
              <div className="h-3 w-24 rounded bg-muted mb-2" />
              <div className="h-2 w-full rounded bg-muted mb-1" />
              <div className="h-2 w-5/6 rounded bg-muted mb-1" />
              <div className="h-2 w-4/6 rounded bg-muted" />
            </div>
          ))}
        </div>
      )}

      {!runEval.isPending && hasResults && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {evaluations.map((ev) => (
            <EvaluationCard key={ev.id} ev={ev} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvaluationCard({ ev }: { ev: AIEvaluation }) {
  const [open, setOpen] = useState(false);
  const verdictBadge =
    ev.verdict === "good"
      ? { variant: "success" as const, label: "Good" }
      : ev.verdict === "bad"
        ? { variant: "destructive" as const, label: "Bad" }
        : ev.verdict === "mixed"
          ? { variant: "muted" as const, label: "Mixed" }
          : null;

  const modelLab = ev.model.split("/")[0];
  const modelName = ev.model.split("/").slice(1).join("/") || ev.model;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-xs">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {modelLab}
          </span>
          <span className="font-medium text-sm">{modelName}</span>
        </div>
        {verdictBadge && (
          <Badge variant={verdictBadge.variant}>{verdictBadge.label}</Badge>
        )}
      </div>

      {ev.status === "error" ? (
        <div className="text-destructive">{ev.error || "Failed"}</div>
      ) : (
        <>
          {typeof ev.score === "number" && (
            <div>
              <div className="flex items-baseline justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  Score
                </span>
                <span className="num font-semibold">{ev.score}/100</span>
              </div>
              <div className="h-1.5 w-full rounded bg-muted">
                <div
                  className={cn(
                    "h-1.5 rounded",
                    ev.score >= 67
                      ? "bg-success"
                      : ev.score >= 34
                        ? "bg-muted-foreground"
                        : "bg-destructive",
                  )}
                  style={{ width: `${Math.max(2, Math.min(100, ev.score))}%` }}
                />
              </div>
            </div>
          )}

          {ev.summary && (
            <p className="text-foreground/90 leading-relaxed">{ev.summary}</p>
          )}

          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="self-start text-muted-foreground hover:text-foreground underline text-[10px] uppercase tracking-wider font-mono"
          >
            {open ? "Hide details" : "Details"}
          </button>

          {open && (
            <div className="flex flex-col gap-2">
              <EvalBullets title="Strengths" items={ev.strengths} tone="success" />
              <EvalBullets
                title="Weaknesses"
                items={ev.weaknesses}
                tone="destructive"
              />
              <EvalBullets title="Suggestions" items={ev.suggestions} tone="info" />
            </div>
          )}
        </>
      )}

      <div className="mt-1 flex justify-between gap-2 text-[10px] text-muted-foreground">
        <span>
          {ev.prompt_tokens != null && ev.completion_tokens != null
            ? `${ev.prompt_tokens}+${ev.completion_tokens} tok`
            : ""}
        </span>
        <span>
          {ev.cost_usd != null ? `$${ev.cost_usd.toFixed(4)}` : ""}
        </span>
      </div>
    </div>
  );
}

function EvalBullets({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "success" | "destructive" | "info";
}) {
  if (!items || items.length === 0) return null;
  const color =
    tone === "success"
      ? "text-success"
      : tone === "destructive"
        ? "text-destructive"
        : "text-muted-foreground";
  return (
    <div>
      <div
        className={cn(
          "text-[10px] font-mono uppercase tracking-wider mb-1",
          color,
        )}
      >
        {title}
      </div>
      <ul className="list-disc pl-4 space-y-0.5 text-foreground/90">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  );
}

function DetailField({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className={cn("num font-semibold", className)}>{value}</span>
    </div>
  );
}
