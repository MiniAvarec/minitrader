import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Copy, Pencil, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, StrategyListItem } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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
    try {
      await api.delete(`/strategies/${id}`);
      qc.invalidateQueries({ queryKey: ["strategies"] });
      toast.success("Strategy deleted");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "failed");
    }
  }

  if (isLoading)
    return (
      <div className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
        loading…
      </div>
    );

  const builtins = (data ?? []).filter((s) => s.is_builtin);
  const mine = (data ?? []).filter((s) => s.is_mine);

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      <section className="flex flex-col gap-3">
        <div>
          <h2 className="text-sm font-mono uppercase tracking-wider">Built-in</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Read-only reference strategies. Clone to customize.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {builtins.map((s) => (
            <StrategyCard
              key={s.id}
              s={s}
              actions={
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => nav(`/strategies/${s.id}`)}
                  >
                    View
                  </Button>
                  <Button size="sm" onClick={() => clone(s.id)}>
                    <Copy className="mr-1 h-3 w-3" />
                    Clone
                  </Button>
                </>
              }
              icon={<Star className="h-3.5 w-3.5 text-accent" fill="currentColor" />}
            />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="text-sm font-mono uppercase tracking-wider">My strategies</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Custom strategies you've authored or cloned.
          </p>
        </div>
        {mine.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-center text-sm text-muted-foreground">
              None yet. Clone a built-in above to get started.
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {mine.map((s) => (
              <StrategyCard
                key={s.id}
                s={s}
                actions={
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => remove(s.id)}
                    >
                      <Trash2 className="mr-1 h-3 w-3" />
                      Delete
                    </Button>
                    <Button size="sm" onClick={() => nav(`/strategies/${s.id}`)}>
                      <Pencil className="mr-1 h-3 w-3" />
                      Edit
                    </Button>
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

function StrategyCard({
  s,
  actions,
  icon,
}: {
  s: StrategyListItem;
  actions: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="space-y-1 pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{s.name}</CardTitle>
          {icon}
        </div>
        <Badge variant="muted" className="w-fit normal-case">
          <span className="font-mono">{s.slug}</span>
        </Badge>
      </CardHeader>
      <CardContent className="flex-1 pb-3">
        <CardDescription className="text-xs leading-relaxed">
          {s.description || "No description."}
        </CardDescription>
      </CardContent>
      <CardFooter className="justify-end gap-2 pt-0">{actions}</CardFooter>
    </Card>
  );
}
