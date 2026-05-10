import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  KeyRound,
  Send,
  ShieldAlert,
  Sliders,
  Target,
} from "lucide-react";
import { toast } from "sonner";
import { api, RiskCfg } from "@/api/client";
import { useAuth } from "@/auth";
import StrategyPicker from "@/components/StrategyPicker";
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

export default function Settings() {
  const { me, refresh } = useAuth();
  const qc = useQueryClient();

  // --- API keys
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [testnet, setTestnet] = useState(true);

  const keys = useQuery({
    queryKey: ["keys"],
    queryFn: async () => (await api.get("/keys")).data,
  });

  async function saveKey() {
    try {
      const t = await api.post("/keys/test", {
        exchange: "binance",
        api_key: apiKey,
        api_secret: apiSecret,
        testnet,
      });
      await api.put("/keys", {
        exchange: "binance",
        api_key: apiKey,
        api_secret: apiSecret,
        testnet,
      });
      toast.success(`Saved · USDT balance $${t.data.usdt_balance.toFixed(2)}`);
      setApiKey("");
      setApiSecret("");
      qc.invalidateQueries({ queryKey: ["keys"] });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "failed");
    }
  }

  async function deleteKey() {
    await api.delete("/keys/binance");
    qc.invalidateQueries({ queryKey: ["keys"] });
    toast.success("API key removed");
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
  const stored = keys.data
    ? keys.data
        .filter((k: any) => k.has_key)
        .map((k: any) => `${k.exchange}${k.testnet ? " (testnet)" : ""}`)
        .join(", ") || null
    : null;

  return (
    <div className="max-w-4xl">
      <Tabs defaultValue="strategies" orientation="vertical" className="flex flex-col gap-4 md:flex-row md:gap-6">
        <TabsList className="flex h-auto flex-row md:flex-col items-stretch justify-start gap-1 bg-transparent p-0 md:w-52 md:flex-shrink-0 overflow-x-auto md:overflow-visible">
          <SettingsTab value="strategies" icon={<Target className="h-4 w-4" />} label="Strategies" />
          <SettingsTab value="mode" icon={<Sliders className="h-4 w-4" />} label="Trading mode" />
          <SettingsTab value="api" icon={<KeyRound className="h-4 w-4" />} label="Binance API" />
          <SettingsTab value="risk" icon={<ShieldAlert className="h-4 w-4" />} label="Risk" />
          <SettingsTab value="telegram" icon={<Send className="h-4 w-4" />} label="Telegram" />
        </TabsList>

        <div className="flex-1 min-w-0 flex flex-col gap-3">
          <TabsContent value="strategies" className="mt-0">
            <Card>
              <CardHeader>
                <CardTitle>Strategy per symbol</CardTitle>
                <CardDescription>
                  Pick which strategy fires for each tracked symbol. Default uses the built-in <em>Multi-TF Confluence</em>.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <StrategyPicker />
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
            <Card>
              <CardHeader>
                <CardTitle>Binance API key</CardTitle>
                <CardDescription>
                  Use a futures-enabled, IP-whitelisted key with no withdrawal permission.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="api-key">API key</Label>
                  <Input
                    id="api-key"
                    placeholder="64-char API key"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="font-mono"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="api-secret">API secret</Label>
                  <Input
                    id="api-secret"
                    placeholder="••••••••"
                    type="password"
                    value={apiSecret}
                    onChange={(e) => setApiSecret(e.target.value)}
                    className="font-mono"
                  />
                </div>
                <div className="flex items-center justify-between rounded-md border border-border p-3">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm font-medium">Testnet</span>
                    <span className="text-xs text-muted-foreground">
                      Use testnet.binancefuture.com instead of mainnet.
                    </span>
                  </div>
                  <Switch checked={testnet} onCheckedChange={setTestnet} />
                </div>
                <div className="flex items-center gap-2">
                  <Button onClick={saveKey} disabled={!apiKey || !apiSecret}>
                    Test &amp; save
                  </Button>
                  <Button variant="outline" onClick={deleteKey}>
                    Remove
                  </Button>
                  <div className="ml-auto text-xs text-muted-foreground font-mono uppercase tracking-wider">
                    Stored: {stored ?? "none"}
                  </div>
                </div>
              </CardContent>
            </Card>
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
