import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

export type Me = {
  id: number;
  email: string;
  mode: "signal_only" | "auto_execute";
  telegram_chat_id: string | null;
  is_admin: boolean;
};

export type AdminUserRow = {
  id: number;
  email: string;
  is_admin: boolean;
  is_approved: boolean;
  created_at: string;
};

export async function listAdminUsers(): Promise<AdminUserRow[]> {
  const r = await api.get<AdminUserRow[]>("/admin/users");
  return r.data;
}

export async function approveUser(id: number): Promise<AdminUserRow> {
  const r = await api.post<AdminUserRow>(`/admin/users/${id}/approve`);
  return r.data;
}

export async function rejectUser(id: number): Promise<void> {
  await api.post(`/admin/users/${id}/reject`);
}

export type SignalRow = {
  id: number;
  exchange: string;
  symbol: string;
  side: "buy" | "sell";
  confidence: number;
  entry: number;
  sl: number | null;
  tp: number | null;
  status: string;
  strategy_id: number | null;
  strategy_name: string | null;
  breakdown: Array<{
    tf: string;
    rsi: number | null;
    macd_hist: number | null;
    ema20: number | null;
    ema50: number | null;
    vote: number;
  }>;
  news_refs: Array<{ source: string; headline: string; url: string }>;
  created_at: string;
};

export type NewsRow = {
  source: string;
  headline: string;
  url: string;
  symbols: string[];
  sentiment: number;
  published_at: string;
};

export type OrderRow = {
  id: number;
  signal_id: number | null;
  exchange: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  notional_usdt: number;
  entry_price: number;
  sl: number | null;
  tp: number | null;
  status: string;
  exchange_order_id: string | null;
  created_at: string;
  closed_at: string | null;
  realized_pnl_usdt: number;
};

export type RiskCfg = {
  max_notional_usdt: number;
  daily_loss_limit_usdt: number;
  max_concurrent_positions: number;
  require_sl_tp: boolean;
};

export type StrategyListItem = {
  id: number;
  slug: string;
  name: string;
  description: string;
  is_builtin: boolean;
  is_mine: boolean;
};

export type StrategyDetail = {
  id: number;
  user_id: number | null;
  parent_id: number | null;
  slug: string;
  name: string;
  description: string;
  code: string;
  is_builtin: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

export type StrategySelection = {
  exchange: string;
  symbol: string;
  strategy_id: number;
  enabled: boolean;
};

export type BacktestTrade = {
  entry_time: string;
  exit_time: string;
  side: "buy" | "sell";
  entry: number;
  exit: number;
  sl: number | null;
  tp: number | null;
  pnl_pct: number;
  pnl_usdt: number;
  outcome: "tp" | "sl" | "timeout";
};

export type BacktestResult = {
  exchange?: string;
  symbol: string;
  hours: number;
  win_rate: number;
  total_pnl_usdt: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  trades: BacktestTrade[];
  equity_curve: { t: number; equity: number }[];
};

export type RebalancePlan = {
  run_id: number;
  total_exposure_usdt: number;
  by_exchange: Record<string, number>;
  by_asset: Record<string, number>;
  intents: Array<{
    exchange: string;
    symbol: string;
    base: string;
    side: "buy" | "sell";
    notional_usdt: number;
    qty: number;
    reduce_only: boolean;
    reason: string;
  }>;
  warnings: string[];
  can_execute: boolean;
  executions?: Array<{ ok: boolean; reason: string; order_id: number | null }>;
};

export type RouteCandidate = {
    exchange: string;
    symbol: string;
    ok: boolean;
    expected_price: number | null;
    mark_price: number | null;
    spread_bps: number | null;
    slippage_bps: number | null;
    fee_usdt: number | null;
    total_cost_usdt: number | null;
    reason: string;
};

export type RouteResult = {
  run_id: number;
  request: { symbol: string; side: "buy" | "sell"; notional_usdt: number };
  candidates: RouteCandidate[];
  best: RouteCandidate | null;
  can_execute: boolean;
  execution?: { ok: boolean; reason: string; order_id: number | null };
};

export type OptimizerResult = {
  run_id: number;
  exchange: string;
  symbol: string;
  best: OptimizerCandidate | null;
  candidates: OptimizerCandidate[];
};

export type OptimizerCandidate = {
  params: Record<string, unknown>;
  score: number;
  stability: number;
  train: {
    trades: number;
    win_rate: number;
    total_pnl_usdt: number;
    total_pnl_pct: number;
    max_drawdown_pct: number;
  };
  validation: {
    trades: number;
    win_rate: number;
    total_pnl_usdt: number;
    total_pnl_pct: number;
    max_drawdown_pct: number;
  };
};

export type ScenarioResult = {
  run_id: number;
  positions: Array<{
    symbol: string;
    base: string;
    side: string;
    shock_pct: number;
    notional_usdt: number;
    pnl_usdt: number;
  }>;
  total_pnl_usdt: number;
  projected_daily_pnl_usdt: number;
  daily_loss_limit_usdt: number;
  daily_loss_usage: number;
  daily_loss_breached: boolean;
  max_drawdown_estimate_pct: number;
  preset: string;
  price_shocks: Record<string, number>;
};

export type ExchangeInfo = {
  id: string;
  label: string;
  has_key: boolean;
  testnet: boolean;
};

export type Instrument = {
  exchange: string;
  symbol: string;
  base: string;
  quote: string;
  tick_size: number;
  lot_size: number;
  min_qty: number;
  min_notional: number;
  ccxt_symbol: string;
};

export type WatchlistEntry = Instrument & {
  enabled: boolean;
};

export async function getExchanges(): Promise<ExchangeInfo[]> {
  const r = await api.get<ExchangeInfo[]>("/exchanges");
  return r.data;
}

export async function searchInstruments(
  exchange: string,
  search: string,
  limit = 50,
): Promise<Instrument[]> {
  const r = await api.get<Instrument[]>(`/exchanges/${exchange}/instruments`, {
    params: { search, limit },
  });
  return r.data;
}

export async function getWatchlist(): Promise<WatchlistEntry[]> {
  const r = await api.get<WatchlistEntry[]>("/watchlist");
  return r.data;
}

export async function addWatchlist(exchange: string, symbol: string): Promise<void> {
  await api.post("/watchlist", { exchange, symbol });
}

export async function removeWatchlist(exchange: string, symbol: string): Promise<void> {
  await api.delete(`/watchlist/${exchange}/${symbol}`);
}

export type FearGreed = {
  value: number;
  classification: string;
  fetched_at: string;
};

export async function getFearGreed(): Promise<FearGreed | null> {
  try {
    const r = await api.get<FearGreed>("/sentiment/fear-greed");
    return r.data;
  } catch {
    return null;
  }
}

export type IntegrationStatus = {
  slug: string;
  label: string;
  description: string;
  secret: boolean;
  in_db: boolean;
  in_env: boolean;
  updated_at: string | null;
  value?: string; // present only for non-secret entries
};

export async function listIntegrations(): Promise<IntegrationStatus[]> {
  const r = await api.get<IntegrationStatus[]>("/integrations");
  return r.data;
}

export async function saveIntegration(slug: string, value: string): Promise<IntegrationStatus> {
  const r = await api.put<IntegrationStatus>(`/integrations/${slug}`, { value });
  return r.data;
}

export async function deleteIntegration(slug: string): Promise<IntegrationStatus> {
  const r = await api.delete<IntegrationStatus>(`/integrations/${slug}`);
  return r.data;
}

export async function testIntegration(slug: string, value: string): Promise<{ ok: boolean; detail: string }> {
  const r = await api.post<{ ok: boolean; detail: string }>(`/integrations/${slug}/test`, { value });
  return r.data;
}
