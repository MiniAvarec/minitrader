import { useEffect, useRef } from "react";
import { createChart, IChartApi, Time } from "lightweight-charts";
import { BacktestResult } from "../api/client";

export default function BacktestPanel({ result }: { result: BacktestResult | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: "#09090b" }, textColor: "#a1a1aa" },
      grid: { vertLines: { color: "#27272a" }, horzLines: { color: "#27272a" } },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const s = chart.addLineSeries({ color: "#10b981", lineWidth: 2 });
    chartRef.current = chart;
    if (result?.equity_curve?.length) {
      s.setData(
        result.equity_curve.map((p) => ({
          time: (Math.floor(p.t / 1000) as unknown) as Time,
          value: p.equity,
        })),
      );
    }
    return () => chart.remove();
  }, [result]);

  if (!result) return <div className="text-sm text-zinc-500">Run a backtest to see results.</div>;

  const winColor = result.win_rate >= 0.5 ? "text-emerald-400" : "text-rose-400";
  const pnlColor = result.total_pnl_usdt >= 0 ? "text-emerald-400" : "text-rose-400";

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-4 gap-3">
        <Stat label="Trades" value={String(result.trades.length)} />
        <Stat label="Win rate" value={`${(result.win_rate * 100).toFixed(0)}%`} className={winColor} />
        <Stat
          label="Total PnL"
          value={`$${result.total_pnl_usdt.toFixed(2)} (${(result.total_pnl_pct * 100).toFixed(1)}%)`}
          className={pnlColor}
        />
        <Stat label="Max DD" value={`${(result.max_drawdown_pct * 100).toFixed(1)}%`} />
      </div>
      <div ref={ref} className="h-48 border border-zinc-800 rounded" />
      <div className="overflow-x-auto max-h-72">
        <table className="w-full text-xs">
          <thead className="text-zinc-500">
            <tr>
              <th className="text-left p-1">Entry</th>
              <th className="text-left p-1">Side</th>
              <th className="text-right p-1">Entry</th>
              <th className="text-right p-1">Exit</th>
              <th className="text-right p-1">PnL %</th>
              <th className="text-right p-1">PnL $</th>
              <th className="text-left p-1">Out</th>
            </tr>
          </thead>
          <tbody>
            {result.trades.map((t, i) => (
              <tr key={i} className="border-t border-zinc-800">
                <td className="p-1 text-zinc-400">{new Date(t.entry_time).toLocaleString()}</td>
                <td className="p-1">{t.side}</td>
                <td className="p-1 text-right font-mono">{t.entry.toFixed(2)}</td>
                <td className="p-1 text-right font-mono">{t.exit.toFixed(2)}</td>
                <td
                  className={`p-1 text-right font-mono ${t.pnl_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  {(t.pnl_pct * 100).toFixed(2)}%
                </td>
                <td
                  className={`p-1 text-right font-mono ${t.pnl_usdt >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  {t.pnl_usdt.toFixed(2)}
                </td>
                <td className="p-1">{t.outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return (
    <div className="border border-zinc-800 rounded p-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={`text-lg font-mono ${className}`}>{value}</div>
    </div>
  );
}
