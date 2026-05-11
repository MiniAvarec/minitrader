import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Lock, Play, Save, XCircle } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  BacktestResult,
  getWatchlist,
  StrategyDetail,
  WatchlistEntry,
} from "@/api/client";
import StrategyEditor from "@/components/StrategyEditor";
import BacktestPanel from "@/components/BacktestPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function StrategyEdit() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const qc = useQueryClient();

  const { data: strategy, isLoading } = useQuery<StrategyDetail>({
    queryKey: ["strategy", id],
    queryFn: async () => (await api.get(`/strategies/${id}`)).data,
  });

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [validateMsg, setValidateMsg] = useState<{
    ok: boolean;
    text: string;
  } | null>(null);
  const [bt, setBt] = useState<BacktestResult | null>(null);
  const [btPair, setBtPair] = useState<string>("");
  const [btHours, setBtHours] = useState(168);
  const [btBusy, setBtBusy] = useState(false);

  const { data: watchlist = [] } = useQuery<WatchlistEntry[]>({
    queryKey: ["watchlist"],
    queryFn: getWatchlist,
  });

  useEffect(() => {
    if (!btPair && watchlist.length > 0) {
      setBtPair(`${watchlist[0].exchange}:${watchlist[0].symbol}`);
    }
  }, [watchlist, btPair]);

  useEffect(() => {
    if (strategy) {
      setCode(strategy.code);
      setName(strategy.name);
    }
  }, [strategy]);

  if (isLoading || !strategy)
    return (
      <div className="text-sm font-mono uppercase tracking-wider text-muted-foreground">
        loading…
      </div>
    );
  const editable = !strategy.is_builtin;

  async function validate() {
    const r = await api.post("/strategies/validate", { code });
    if (r.data.ok) {
      setValidateMsg({
        ok: true,
        text: `OK · ${r.data.name} · TFs: ${(r.data.timeframes || []).join(", ") || "—"}`,
      });
    } else {
      setValidateMsg({ ok: false, text: r.data.error });
    }
  }

  async function save() {
    try {
      await api.put(`/strategies/${id}`, { code, name });
      qc.invalidateQueries({ queryKey: ["strategies"] });
      qc.invalidateQueries({ queryKey: ["strategy", id] });
      toast.success("Saved");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "failed");
    }
  }

  async function runBacktest() {
    if (!btPair) return;
    const [exchange, symbol] = btPair.split(":");
    setBtBusy(true);
    setBt(null);
    try {
      const r = await api.post(`/strategies/${id}/backtest`, {
        exchange,
        symbol,
        hours: btHours,
        notional_usdt: 100,
      });
      setBt(r.data);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "backtest failed");
    } finally {
      setBtBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-12 gap-4 max-w-[1600px]">
      <div className="col-span-12 xl:col-span-7 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => nav("/strategies")}
            className="h-8"
          >
            <ArrowLeft className="mr-1 h-3 w-3" />
            Back
          </Button>
          <Input
            disabled={!editable}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="flex-1 font-mono"
          />
          {strategy.is_builtin && (
            <Badge variant="muted" className="gap-1">
              <Lock className="h-3 w-3" />
              read-only
            </Badge>
          )}
        </div>

        <Card>
          <CardContent className="p-0">
            <StrategyEditor value={code} onChange={setCode} readOnly={!editable} />
          </CardContent>
        </Card>

        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="outline" size="sm" onClick={validate}>
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Validate
          </Button>
          {editable && (
            <Button size="sm" onClick={save}>
              <Save className="mr-1 h-3 w-3" />
              Save
            </Button>
          )}
          {validateMsg && (
            <Badge
              variant={validateMsg.ok ? "success" : "destructive"}
              className="gap-1 normal-case"
            >
              {validateMsg.ok ? (
                <CheckCircle2 className="h-3 w-3" />
              ) : (
                <XCircle className="h-3 w-3" />
              )}
              <span className="font-mono text-[10px]">{validateMsg.text}</span>
            </Badge>
          )}
        </div>
      </div>

      <div className="col-span-12 xl:col-span-5 flex flex-col gap-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="font-mono uppercase tracking-wider">
              Backtest
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex flex-col gap-1">
                <Label htmlFor="bt-symbol">Pair</Label>
                <Select value={btPair} onValueChange={setBtPair}>
                  <SelectTrigger id="bt-symbol" className="w-48">
                    <SelectValue placeholder="Add a pair…" />
                  </SelectTrigger>
                  <SelectContent>
                    {watchlist.map((p) => (
                      <SelectItem
                        key={`${p.exchange}:${p.symbol}`}
                        value={`${p.exchange}:${p.symbol}`}
                      >
                        {p.exchange.toUpperCase()} · {p.symbol}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="bt-hours">Window</Label>
                <Select
                  value={String(btHours)}
                  onValueChange={(v) => setBtHours(parseInt(v))}
                >
                  <SelectTrigger id="bt-hours" className="w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="24">24h</SelectItem>
                    <SelectItem value="72">3d</SelectItem>
                    <SelectItem value="168">7d</SelectItem>
                    <SelectItem value="720">30d</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                onClick={runBacktest}
                disabled={btBusy}
                className="ml-auto self-end"
              >
                <Play className="mr-1 h-3 w-3" />
                {btBusy ? "running…" : "Run"}
              </Button>
            </div>
            <BacktestPanel result={bt} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
