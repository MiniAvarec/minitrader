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
  symbol: string;
  hours: number;
  win_rate: number;
  total_pnl_usdt: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  trades: BacktestTrade[];
  equity_curve: { t: number; equity: number }[];
};
