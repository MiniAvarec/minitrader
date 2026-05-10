import { useQuery } from "@tanstack/react-query";
import { api, NewsRow } from "../api/client";

export default function NewsPanel() {
  const { data } = useQuery<NewsRow[]>({
    queryKey: ["news"],
    queryFn: async () => (await api.get("/news?hours=6")).data,
    refetchInterval: 60_000,
  });
  return (
    <div className="flex flex-col gap-1">
      {(data ?? []).slice(0, 30).map((n, i) => (
        <a
          key={i}
          href={n.url}
          target="_blank"
          rel="noreferrer"
          className="text-sm border border-zinc-800 rounded p-2 hover:bg-zinc-900"
        >
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span
              className={`px-1.5 rounded ${
                n.sentiment > 0.2
                  ? "bg-emerald-900/50 text-emerald-300"
                  : n.sentiment < -0.2
                  ? "bg-rose-900/50 text-rose-300"
                  : "bg-zinc-800"
              }`}
            >
              {n.sentiment > 0 ? "+" : ""}
              {n.sentiment.toFixed(2)}
            </span>
            <span>{n.source}</span>
            <span>{new Date(n.published_at).toLocaleTimeString()}</span>
            {n.symbols.length > 0 && (
              <span className="text-zinc-400">{n.symbols.join(", ")}</span>
            )}
          </div>
          <div>{n.headline}</div>
        </a>
      ))}
      {data && data.length === 0 && (
        <div className="text-zinc-500 text-sm">No news in the last 6 hours.</div>
      )}
    </div>
  );
}
