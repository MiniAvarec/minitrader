import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, StrategyListItem } from "../api/client";

export default function Strategies() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<StrategyListItem[]>({
    queryKey: ["strategies"],
    queryFn: async () => (await api.get("/strategies")).data,
  });

  async function clone(id: number) {
    const r = await api.post(`/strategies/${id}/clone`);
    qc.invalidateQueries({ queryKey: ["strategies"] });
    nav(`/strategies/${r.data.id}`);
  }

  async function remove(id: number) {
    if (!confirm("Delete this strategy?")) return;
    await api.delete(`/strategies/${id}`);
    qc.invalidateQueries({ queryKey: ["strategies"] });
  }

  if (isLoading) return <div>loading…</div>;

  const builtins = (data ?? []).filter((s) => s.is_builtin);
  const mine = (data ?? []).filter((s) => s.is_mine);

  return (
    <div className="grid grid-cols-1 gap-6 max-w-4xl">
      <section>
        <h2 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">Built-in</h2>
        <div className="grid grid-cols-1 gap-2">
          {builtins.map((s) => (
            <Card
              key={s.id}
              s={s}
              actions={
                <>
                  <button
                    onClick={() => nav(`/strategies/${s.id}`)}
                    className="text-xs px-2 py-1 border border-zinc-700 rounded"
                  >
                    View
                  </button>
                  <button
                    onClick={() => clone(s.id)}
                    className="text-xs px-2 py-1 bg-emerald-700 rounded"
                  >
                    Clone & edit
                  </button>
                </>
              }
            />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">My strategies</h2>
        {mine.length === 0 ? (
          <div className="text-sm text-zinc-500">
            None yet. Clone a built-in above to get started.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2">
            {mine.map((s) => (
              <Card
                key={s.id}
                s={s}
                actions={
                  <>
                    <button
                      onClick={() => nav(`/strategies/${s.id}`)}
                      className="text-xs px-2 py-1 bg-zinc-200 text-zinc-900 rounded"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => remove(s.id)}
                      className="text-xs px-2 py-1 border border-zinc-700 rounded"
                    >
                      Delete
                    </button>
                  </>
                }
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Card({ s, actions }: { s: StrategyListItem; actions: React.ReactNode }) {
  return (
    <div className="border border-zinc-800 rounded p-3 flex items-center justify-between gap-3">
      <div className="flex-1 min-w-0">
        <div className="font-medium">{s.name}</div>
        <div className="text-xs text-zinc-500 truncate">{s.description}</div>
        <div className="text-xs text-zinc-600">
          slug: <code>{s.slug}</code>
        </div>
      </div>
      <div className="flex gap-2">{actions}</div>
    </div>
  );
}
