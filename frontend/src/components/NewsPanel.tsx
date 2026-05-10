import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, NewsRow } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export default function NewsPanel() {
  const { data } = useQuery<NewsRow[]>({
    queryKey: ["news"],
    queryFn: async () => (await api.get("/news?hours=6")).data,
    refetchInterval: 60_000,
  });

  if (!data) return null;
  if (data.length === 0)
    return (
      <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        No news in the last 6 hours.
      </div>
    );

  return (
    <div className="flex flex-col divide-y divide-border rounded-md border border-border bg-card">
      {data.slice(0, 30).map((n, i) => {
        const variant: "success" | "destructive" | "muted" =
          n.sentiment > 0.2 ? "success" : n.sentiment < -0.2 ? "destructive" : "muted";
        return (
          <a
            key={i}
            href={n.url}
            target="_blank"
            rel="noreferrer"
            className="group flex flex-col gap-1 p-3 transition-colors hover:bg-muted/40"
          >
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <Badge variant={variant} className="num">
                {n.sentiment > 0 ? "+" : ""}
                {n.sentiment.toFixed(2)}
              </Badge>
              <span>{n.source}</span>
              <span>{new Date(n.published_at).toLocaleTimeString()}</span>
              {n.symbols.length > 0 && (
                <span className={cn("text-foreground")}>{n.symbols.join(", ")}</span>
              )}
              <ExternalLink className="ml-auto h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
            </div>
            <div className="text-sm leading-snug">{n.headline}</div>
          </a>
        );
      })}
    </div>
  );
}
