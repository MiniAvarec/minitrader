import { useEffect, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { BacktestResult } from "@/api/client";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { useChartTheme } from "@/lib/useChartTheme";
import { cn } from "@/lib/utils";

export default function BacktestPanel({ result }: { result: BacktestResult | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
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
    const s = chart.addLineSeries({ color: theme.primary, lineWidth: 2 });
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
    series.applyOptions({ color: theme.primary });
  }, [theme]);

  useEffect(() => {
    if (!seriesRef.current) return;
    if (result?.equity_curve?.length) {
      seriesRef.current.setData(
        result.equity_curve.map((p) => ({
          time: (Math.floor(p.t / 1000) as unknown) as Time,
          value: p.equity,
        })),
      );
    } else {
      seriesRef.current.setData([]);
    }
  }, [result]);

  if (!result)
    return (
      <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        Run a backtest to see results.
      </div>
    );

  const winColor = result.win_rate >= 0.5 ? "text-success" : "text-destructive";
  const pnlColor = result.total_pnl_usdt >= 0 ? "text-success" : "text-destructive";

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat label="Trades" value={String(result.trades.length)} />
        <Stat
          label="Win rate"
          value={`${(result.win_rate * 100).toFixed(0)}%`}
          className={winColor}
        />
        <Stat
          label="Total PnL"
          value={`$${result.total_pnl_usdt.toFixed(2)}`}
          sub={`${(result.total_pnl_pct * 100).toFixed(1)}%`}
          className={pnlColor}
        />
        <Stat
          label="Max DD"
          value={`${(result.max_drawdown_pct * 100).toFixed(1)}%`}
        />
      </div>
      <div ref={ref} className="h-48 rounded-md border border-border bg-card" />
      <div className="rounded-md border border-border max-h-72 overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 bg-card">
            <TableRow>
              <TableHead>Entry</TableHead>
              <TableHead>Side</TableHead>
              <TableHead className="text-right">Entry $</TableHead>
              <TableHead className="text-right">Exit $</TableHead>
              <TableHead className="text-right">PnL %</TableHead>
              <TableHead className="text-right">PnL $</TableHead>
              <TableHead>Out</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.trades.map((t, i) => (
              <TableRow key={i}>
                <TableCell className="text-muted-foreground text-xs">
                  {new Date(t.entry_time).toLocaleString()}
                </TableCell>
                <TableCell className="uppercase text-xs">{t.side}</TableCell>
                <TableCell className="text-right num">{t.entry.toFixed(2)}</TableCell>
                <TableCell className="text-right num">{t.exit.toFixed(2)}</TableCell>
                <TableCell
                  className={cn(
                    "text-right num",
                    t.pnl_pct >= 0 ? "text-success" : "text-destructive",
                  )}
                >
                  {(t.pnl_pct * 100).toFixed(2)}%
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right num",
                    t.pnl_usdt >= 0 ? "text-success" : "text-destructive",
                  )}
                >
                  {t.pnl_usdt.toFixed(2)}
                </TableCell>
                <TableCell className="uppercase text-xs">{t.outcome}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
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
      <CardContent className="p-3 pt-3">
        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className={cn("text-lg num font-semibold", className)}>{value}</div>
        {sub && <div className={cn("text-xs num", className)}>{sub}</div>}
      </CardContent>
    </Card>
  );
}
