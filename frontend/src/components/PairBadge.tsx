import { cn } from "@/lib/utils";

const COLORS: Record<string, string> = {
  binance: "bg-yellow-500/10 text-yellow-500 border-yellow-500/30",
  okx: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  bybit: "bg-orange-500/10 text-orange-400 border-orange-500/30",
};

export default function PairBadge({
  exchange,
  symbol,
  className,
}: {
  exchange: string;
  symbol: string;
  className?: string;
}) {
  const colors = COLORS[exchange] ?? "bg-muted text-muted-foreground border-border";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider",
        colors,
        className,
      )}
    >
      <span className="opacity-75">{exchange}</span>
      <span>·</span>
      <span className="font-semibold">{symbol}</span>
    </span>
  );
}
