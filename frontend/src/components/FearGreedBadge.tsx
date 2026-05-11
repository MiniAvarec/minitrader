import { useQuery } from "@tanstack/react-query";
import { Gauge } from "lucide-react";
import { getFearGreed } from "@/api/client";
import { cn } from "@/lib/utils";

function bandColor(value: number): string {
  // alternative.me bands: 0-25 extreme fear, 25-45 fear, 45-55 neutral,
  // 55-75 greed, 75-100 extreme greed.
  if (value < 25) return "bg-destructive/10 text-destructive border-destructive/30";
  if (value < 45) return "bg-orange-500/10 text-orange-400 border-orange-500/30";
  if (value < 55) return "bg-muted text-muted-foreground border-border";
  if (value < 75) return "bg-success/10 text-success border-success/30";
  return "bg-emerald-500/15 text-emerald-400 border-emerald-500/40";
}

export default function FearGreedBadge({ className }: { className?: string }) {
  const { data } = useQuery({
    queryKey: ["sentiment", "fear-greed"],
    queryFn: getFearGreed,
    refetchInterval: 60 * 60 * 1000, // index updates daily; once an hour is plenty
    staleTime: 30 * 60 * 1000,
  });

  if (!data) {
    return null;
  }

  return (
    <span
      title={`Fear & Greed Index — ${data.classification} (${new Date(data.fetched_at).toLocaleString()})`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider",
        bandColor(data.value),
        className,
      )}
    >
      <Gauge className="h-3 w-3" />
      <span className="opacity-75">F&amp;G</span>
      <span className="font-semibold tabular-nums">{Math.round(data.value)}</span>
      <span className="hidden opacity-75 sm:inline">· {data.classification}</span>
    </span>
  );
}
