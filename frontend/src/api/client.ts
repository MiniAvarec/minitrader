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
};

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
