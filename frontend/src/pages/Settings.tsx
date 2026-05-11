import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  KeyRound,
  Newspaper,
  Send,
  ShieldAlert,
  Sliders,
  Target,
} from "lucide-react";
import { toast } from "sonner";
import {
  api,
  deleteIntegration,
  IntegrationStatus,
  listIntegrations,
  RiskCfg,
  saveIntegration,
  testIntegration,
} from "@/api/client";
import { useAuth } from "@/auth";
import AddPairDialog from "@/components/AddPairDialog";
import PairBadge from "@/components/PairBadge";
import StrategyPicker from "@/components/StrategyPicker";
import {
  getWatchlist,
  removeWatchlist,
  WatchlistEntry,
} from "@/api/client";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

type KeyStatus = {
  exchange: string;
  label: string;
  has_key: boolean;
  testnet: boolean | null;
};

const EXCHANGES: { id: string; label: string; needsPassphrase: boolean }[] = [
  { id: "binance", label: "Binance USDT-M Futures", needsPassphrase: false },
  { id: "okx", label: "OKX Perpetual Swaps", needsPassphrase: true },
  { id: "bybit", label: "Bybit Linear Perps", needsPassphrase: false },
];

export default function Settings() {
  const { me, refresh } = useAuth();
  const qc = useQueryClient();

  const keys = useQuery<KeyStatus[]>({
    queryKey: ["keys"],
    queryFn: async () => (await api.get("/keys")).data,
  });

  const watchlist = useQuery<WatchlistEntry[]>({
    queryKey: ["watchlist"],
    queryFn: getWatchlist,
  });

  async function deleteKey(exchange: string) {
    await api.delete(`/keys/${exchange}`);
    qc.invalidateQueries({ queryKey: ["keys"] });
    toast.success(`${exchange} key removed`);
  }

  async function removePair(exchange: string, symbol: string) {
    await removeWatchlist(exchange, symbol);
    qc.invalidateQueries({ queryKey: ["watchlist"] });
  }

  // --- Risk
  const risk = useQuery<RiskCfg>({
    queryKey: ["risk"],
    queryFn: async () => (await api.get("/settings/risk")).data,
  });
  const [r, setR] = useState<RiskCfg | null>(null);
  useEffect(() => {
    if (risk.data) setR(risk.data);
  }, [risk.data]);

  async function saveRisk() {
    if (!r) return;
    await api.put("/settings/risk", r);
    qc.invalidateQueries({ queryKey: ["risk"] });
    toast.success("Risk config saved");
  }

  // --- Mode
  async function setMode(mode: "signal_only" | "auto_execute") {
    await api.put("/settings/mode", { mode });
    await refresh();
  }

  // --- Telegram
  const [linkToken, setLinkToken] = useState<string | null>(null);
  async function linkTelegram() {
    const r = await api.post<{ link_token: string }>("/settings/telegram/link");
    setLinkToken(r.data.link_token);
  }
  async function unlinkTelegram() {
    await api.delete("/settings/telegram");
    await refresh();
    setLinkToken(null);
    toast.success("Telegram unlinked");
  }

  const auto = me?.mode === "auto_execute";

  return (
    <div className="max-w-4xl">
      <Tabs defaultValue="strategies" orientation="vertical" className="flex flex-col gap-4 md:flex-row md:gap-6">
        <TabsList className="flex h-auto flex-row md:flex-col items-stretch justify-start gap-1 bg-transparent p-0 md:w-52 md:flex-shrink-0 overflow-x-auto md:overflow-visible">
          <SettingsTab value="strategies" icon={<Target className="h-4 w-4" />} label="Strategies" />
          <SettingsTab value="pairs" icon={<Target className="h-4 w-4" />} label="Pairs" />
          <SettingsTab value="mode" icon={<Sliders className="h-4 w-4" />} label="Trading mode" />
          <SettingsTab value="api" icon={<KeyRound className="h-4 w-4" />} label="Exchanges" />
          <SettingsTab value="integrations" icon={<Newspaper className="h-4 w-4" />} label="Integrations" />
          <SettingsTab value="risk" icon={<ShieldAlert className="h-4 w-4" />} label="Risk" />
          <SettingsTab value="telegram" icon={<Send className="h-4 w-4" />} label="Telegram" />
        </TabsList>

        <div className="flex-1 min-w-0 flex flex-col gap-3">
          <TabsContent value="strategies" className="mt-0">
            <Card>
              <CardHeader>
                <CardTitle>Strategy per pair</CardTitle>
                <CardDescription>
                  Pick which strategy fires for each tracked (exchange, symbol). Default
                  uses the built-in <em>Multi-TF Confluence</em>.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <StrategyPicker />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="pairs" className="mt-0">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Watchlist</CardTitle>
                  <CardDescription>
                    Add pairs from any connected exchange. The streams manager auto-subscribes.
                  </CardDescription>
                </div>
                <AddPairDialog />
              </CardHeader>
              <CardContent>
                {(!watchlist.data || watchlist.data.length === 0) && (
                  <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
                    No pairs yet.
                  </div>
                )}
                <div className="flex flex-col gap-1">
                  {watchlist.data?.map((p) => (
                    <div
                      key={`${p.exchange}:${p.symbol}`}
                      className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
                    >
                      <div className="flex items-center gap-3">
                        <PairBadge exchange={p.exchange} symbol={p.symbol} />
                        <span className="text-xs text-muted-foreground">
                          tick {p.tick_size} · lot {p.lot_size} · min $
                          {p.min_notional}
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => removePair(p.exchange, p.symbol)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="mode" className="mt-0">
            <Card>
              <CardHeader>
                <CardTitle>Trading mode</CardTitle>
                <CardDescription>
                  Auto-execute places real orders for every signal that passes risk checks. Use testnet first.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex items-center justify-between rounded-md border border-border p-3">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm font-medium">Auto-execute orders</span>
                    <span className="text-xs text-muted-foreground">
                      {auto
                        ? "Live: signals are placed automatically."
                        : "Disabled: you'll execute manually from the feed."}
                    </span>
                  </div>
                  <Switch
                    checked={auto}
                    onCheckedChange={(v) => setMode(v ? "auto_execute" : "signal_only")}
                  />
                </div>
                {auto && (
                  <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>
                      Auto-execute is on. Verify your API key is testnet-only or your risk config matches your appetite.
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="api" className="mt-0">
            <div className="flex flex-col gap-3">
              {EXCHANGES.map((ex) => {
                const status = keys.data?.find((k) => k.exchange === ex.id);
                return (
                  <ExchangeKeyCard
                    key={ex.id}
                    exchange={ex}
                    status={status}
                    onDelete={() => deleteKey(ex.id)}
                    onSaved={() => qc.invalidateQueries({ queryKey: ["keys"] })}
                  />
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="integrations" className="mt-0">
            <IntegrationsTab />
          </TabsContent>

          <TabsContent value="risk" className="mt-0">
            <Card>
              <CardHeader>
                <CardTitle>Risk controls</CardTitle>
                <CardDescription>
                  Hard limits enforced before any auto-execute order is sent.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {r && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1.5">
                      <Label>Per-trade max notional (USDT)</Label>
                      <Input
                        type="number"
                        value={r.max_notional_usdt}
                        onChange={(e) =>
                          setR({ ...r, max_notional_usdt: parseFloat(e.target.value) || 0 })
                        }
                        className="num"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label>Daily loss limit (USDT)</Label>
                      <Input
                        type="number"
                        value={r.daily_loss_limit_usdt}
                        onChange={(e) =>
                          setR({ ...r, daily_loss_limit_usdt: parseFloat(e.target.value) || 0 })
                        }
                        className="num"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label>Max concurrent positions</Label>
                      <Input
                        type="number"
                        value={r.max_concurrent_positions}
                        onChange={(e) =>
                          setR({
                            ...r,
                            max_concurrent_positions: parseInt(e.target.value, 10) || 0,
                          })
                        }
                        className="num"
                      />
                    </div>
                    <div className="flex items-center justify-between rounded-md border border-border p-3 md:col-span-1">
                      <div>
                        <div className="text-sm font-medium">Require SL/TP</div>
                        <div className="text-xs text-muted-foreground">
                          Reject auto-executes without stops.
                        </div>
                      </div>
                      <Switch
                        checked={r.require_sl_tp}
                        onCheckedChange={(v) => setR({ ...r, require_sl_tp: v })}
                      />
                    </div>
                    <Button onClick={saveRisk} className="md:col-span-2 mt-2">
                      Save risk config
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="telegram" className="mt-0">
            <Card>
              <CardHeader>
                <CardTitle>Telegram</CardTitle>
                <CardDescription>
                  Receive signal pushes to your Telegram chat.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {me?.telegram_chat_id ? (
                  <div className="flex items-center justify-between rounded-md border border-border p-3">
                    <div className="text-sm">
                      Linked to chat{" "}
                      <Badge variant="muted" className="font-mono normal-case">
                        {me.telegram_chat_id}
                      </Badge>
                    </div>
                    <Button variant="outline" onClick={unlinkTelegram}>
                      Unlink
                    </Button>
                  </div>
                ) : (
                  <>
                    <Button onClick={linkTelegram} className="w-fit">
                      Generate link token
                    </Button>
                    {linkToken && (
                      <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                        In Telegram, message the bot:{" "}
                        <code className="rounded bg-background px-2 py-0.5 font-mono">
                          /start {linkToken}
                        </code>
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

function SettingsTab({
  value,
  icon,
  label,
}: {
  value: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <TabsTrigger
      value={value}
      className="justify-start gap-2 px-3 data-[state=active]:bg-muted data-[state=active]:shadow-none"
    >
      {icon}
      <span>{label}</span>
    </TabsTrigger>
  );
}

function IntegrationsTab() {
  const qc = useQueryClient();
  const integrations = useQuery<IntegrationStatus[]>({
    queryKey: ["integrations"],
    queryFn: listIntegrations,
  });

  async function remove(slug: string) {
    await deleteIntegration(slug);
    qc.invalidateQueries({ queryKey: ["integrations"] });
    toast.success("Removed");
  }

  return (
    <div className="flex flex-col gap-3">
      <Card>
        <CardHeader>
          <CardTitle>News &amp; sentiment integrations</CardTitle>
          <CardDescription>
            System-wide keys used by the news worker and signal engine. Stored
            encrypted in the database. <code>.env</code> values still work as
            a fallback for fresh deployments.
          </CardDescription>
        </CardHeader>
      </Card>
      {integrations.data?.map((status) => (
        <IntegrationCard
          key={status.slug}
          status={status}
          onDelete={() => remove(status.slug)}
          onSaved={() => qc.invalidateQueries({ queryKey: ["integrations"] })}
        />
      ))}
    </div>
  );
}

function IntegrationCard({
  status,
  onDelete,
  onSaved,
}: {
  status: IntegrationStatus;
  onDelete: () => void;
  onSaved: () => void;
}) {
  const [value, setValue] = useState(status.value ?? "");
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!value.trim()) return;
    setBusy(true);
    try {
      const t = await testIntegration(status.slug, value.trim());
      await saveIntegration(status.slug, value.trim());
      toast.success(`${status.label}: ${t.detail}`);
      if (status.secret) setValue("");
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  }

  const sourceLabel = status.in_db
    ? "Stored in DB"
    : status.in_env
      ? "Loaded from .env"
      : "Not set";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>{status.label}</CardTitle>
          <CardDescription>
            {status.description}{" "}
            <Badge variant="muted" className="ml-1 normal-case">
              {sourceLabel}
            </Badge>
          </CardDescription>
        </div>
        {status.in_db && (
          <Button variant="outline" size="sm" onClick={onDelete}>
            Remove
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>{status.secret ? "API key" : "Value"}</Label>
          <Input
            type={status.secret ? "password" : "text"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="font-mono"
            placeholder={
              status.secret
                ? status.in_db
                  ? "•••••••• (enter a new key to replace)"
                  : status.in_env
                    ? "Loaded from environment — enter to override"
                    : "Paste API key"
                : "Value"
            }
          />
        </div>
        <Button
          onClick={save}
          disabled={busy || !value.trim()}
          className="w-fit"
        >
          {busy ? "Testing…" : "Test & save"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ExchangeKeyCard({
  exchange,
  status,
  onDelete,
  onSaved,
}: {
  exchange: { id: string; label: string; needsPassphrase: boolean };
  status?: KeyStatus;
  onDelete: () => void;
  onSaved: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [testnet, setTestnet] = useState(true);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const body: any = {
        exchange: exchange.id,
        api_key: apiKey,
        api_secret: apiSecret,
        testnet,
      };
      if (exchange.needsPassphrase) body.passphrase = passphrase;
      const t = await api.post("/keys/test", body);
      await api.put("/keys", body);
      toast.success(
        `${exchange.label} saved · USDT balance $${t.data.usdt_balance.toFixed(2)}`,
      );
      setApiKey("");
      setApiSecret("");
      setPassphrase("");
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "failed");
    } finally {
      setBusy(false);
    }
  }

  const stored = status?.has_key;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>{exchange.label}</CardTitle>
          <CardDescription>
            {stored ? (
              <>
                Stored{" "}
                <Badge variant="muted" className="ml-1 normal-case">
                  {status?.testnet ? "testnet" : "live"}
                </Badge>
              </>
            ) : (
              "No key on file."
            )}
          </CardDescription>
        </div>
        {stored && (
          <Button variant="outline" size="sm" onClick={onDelete}>
            Remove
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>API key</Label>
          <Input
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="font-mono"
            placeholder="API key"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>API secret</Label>
          <Input
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            className="font-mono"
            placeholder="••••••••"
          />
        </div>
        {exchange.needsPassphrase && (
          <div className="flex flex-col gap-1.5">
            <Label>Passphrase</Label>
            <Input
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              className="font-mono"
              placeholder="••••••••"
            />
          </div>
        )}
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium">Testnet</span>
            <span className="text-xs text-muted-foreground">
              Use the sandbox endpoint instead of mainnet.
            </span>
          </div>
          <Switch checked={testnet} onCheckedChange={setTestnet} />
        </div>
        <Button
          onClick={save}
          disabled={
            busy ||
            !apiKey ||
            !apiSecret ||
            (exchange.needsPassphrase && !passphrase)
          }
          className="w-fit"
        >
          {busy ? "Testing…" : "Test & save"}
        </Button>
      </CardContent>
    </Card>
  );
}
