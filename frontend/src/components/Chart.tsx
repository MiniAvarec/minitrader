import { useEffect, useRef, useState } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  Time,
  HistogramData,
} from "lightweight-charts";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp } from "lucide-react";
import { api } from "@/api/client";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChartTheme } from "@/lib/useChartTheme";
import { cn } from "@/lib/utils";

const TFS = ["1m", "3m", "15m", "1h"] as const;
type Tf = (typeof TFS)[number];

type KlineRow = {
  open_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export default function Chart({
  exchange,
  symbol,
  height = 380,
  withVolume = true,
}: {
  exchange: string;
  symbol: string;
  height?: number;
  withVolume?: boolean;
}) {
  const [tf, setTf] = useState<Tf>("15m");
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const theme = useChartTheme();

  const { data } = useQuery<{ klines: KlineRow[] }>({
    queryKey: ["klines", exchange, symbol, tf],
    queryFn: async () =>
      (await api.get(`/klines/${exchange}/${symbol}/${tf}`)).data,
    refetchInterval: 30_000,
    enabled: Boolean(exchange && symbol),
  });

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
      crosshair: { mode: 1 },
    });
    const series = chart.addCandlestickSeries({
      upColor: theme.success,
      downColor: theme.destructive,
      borderVisible: false,
      wickUpColor: theme.success,
      wickDownColor: theme.destructive,
    });

    if (withVolume) {
      const vol = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.78, bottom: 0 },
      });
      volRef.current = vol;
    }

    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-skin on theme change.
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
      upColor: theme.success,
      downColor: theme.destructive,
      wickUpColor: theme.success,
      wickDownColor: theme.destructive,
    });
  }, [theme]);

  // Push data + volume.
  useEffect(() => {
    if (!seriesRef.current || !data) return;
    const candles = data.klines.map((k) => ({
      time: (Math.floor(k.open_time / 1000) as unknown) as Time,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
    }));
    seriesRef.current.setData(candles);

    if (volRef.current) {
      const vols: HistogramData[] = data.klines.map((k) => ({
        time: (Math.floor(k.open_time / 1000) as unknown) as Time,
        value: k.volume ?? 0,
        color: k.close >= k.open ? theme.success : theme.destructive,
      }));
      volRef.current.setData(vols);
    }
  }, [data, theme]);

  const last = data?.klines.at(-1);
  const first = data?.klines[0];
  const chg =
    last && first ? ((last.close - first.open) / first.open) * 100 : 0;
  const up = chg >= 0;

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-base font-semibold tracking-wider">
            <span className="text-muted-foreground mr-1.5 text-[10px] uppercase tracking-wider">
              {exchange}
            </span>
            {symbol}
          </span>
          {last && (
            <>
              <span className="num text-lg font-semibold">
                {last.close.toFixed(2)}
              </span>
              <span
                className={cn(
                  "flex items-center gap-0.5 text-xs num",
                  up ? "text-success" : "text-destructive",
                )}
              >
                {up ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
                {chg.toFixed(2)}%
              </span>
            </>
          )}
        </div>
        <Tabs value={tf} onValueChange={(v) => setTf(v as Tf)}>
          <TabsList className="h-7">
            {TFS.map((t) => (
              <TabsTrigger key={t} value={t} className="px-2 text-[10px]">
                {t}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <div
        ref={ref}
        style={{ height }}
        className="flex-1 rounded-md border border-border bg-card"
      />
    </div>
  );
}
