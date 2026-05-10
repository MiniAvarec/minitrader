import { useEffect, useRef, useState } from "react";
import { createChart, IChartApi, CandlestickSeriesPartialOptions, Time } from "lightweight-charts";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

const TFS = ["1m", "3m", "15m", "1h"] as const;
type Tf = (typeof TFS)[number];

type KlineRow = {
  open_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export default function Chart({ symbol }: { symbol: string }) {
  const [tf, setTf] = useState<Tf>("15m");
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<any>(null);

  const { data } = useQuery<{ klines: KlineRow[] }>({
    queryKey: ["klines", symbol, tf],
    queryFn: async () => (await api.get(`/klines/${symbol}/${tf}`)).data,
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: "#09090b" }, textColor: "#a1a1aa" },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const opts: CandlestickSeriesPartialOptions = {
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#f43f5e",
    };
    const series = chart.addCandlestickSeries(opts);
    chartRef.current = chart;
    seriesRef.current = series;
    return () => chart.remove();
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !data) return;
    seriesRef.current.setData(
      data.klines.map((k) => ({
        time: (Math.floor(k.open_time / 1000) as unknown) as Time,
        open: k.open,
        high: k.high,
        low: k.low,
        close: k.close,
      })),
    );
  }, [data]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="font-mono">{symbol}</span>
        <div className="flex gap-1">
          {TFS.map((t) => (
            <button
              key={t}
              onClick={() => setTf(t)}
              className={`text-xs px-2 py-1 rounded border ${
                t === tf
                  ? "bg-zinc-200 text-zinc-900 border-zinc-200"
                  : "border-zinc-700 text-zinc-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <div ref={ref} className="h-72 border border-zinc-800 rounded" />
    </div>
  );
}
