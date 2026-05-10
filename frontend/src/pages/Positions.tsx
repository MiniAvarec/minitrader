import { useQuery } from "@tanstack/react-query";
import { api, OrderRow } from "../api/client";

type LivePositions = {
  usdt_balance: number;
  positions: Array<{
    symbol: string;
    side: string;
    contracts: number;
    notional: number;
    entry_price: number;
    mark_price: number;
    unrealized_pnl: number;
    leverage: number;
  }>;
};

export default function Positions() {
  const positions = useQuery<LivePositions>({
    queryKey: ["positions"],
    queryFn: async () => (await api.get("/positions")).data,
    refetchInterval: 10_000,
    retry: false,
  });
  const orders = useQuery<OrderRow[]>({
    queryKey: ["orders"],
    queryFn: async () => (await api.get("/orders")).data,
    refetchInterval: 30_000,
  });

  return (
    <div className="grid grid-cols-1 gap-6 max-w-6xl">
      <section>
        <h2 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">
          Live positions {positions.data ? `· balance $${positions.data.usdt_balance.toFixed(2)}` : ""}
        </h2>
        {positions.error && (
          <div className="text-sm text-rose-400">
            Could not fetch positions — add Binance API keys in Settings.
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-zinc-500">
              <tr>
                <th className="text-left p-2">Symbol</th>
                <th className="text-left p-2">Side</th>
                <th className="text-right p-2">Qty</th>
                <th className="text-right p-2">Entry</th>
                <th className="text-right p-2">Mark</th>
                <th className="text-right p-2">uPnL</th>
                <th className="text-right p-2">Lev</th>
              </tr>
            </thead>
            <tbody>
              {(positions.data?.positions ?? []).map((p, i) => (
                <tr key={i} className="border-t border-zinc-800">
                  <td className="p-2 font-mono">{p.symbol}</td>
                  <td className="p-2">{p.side}</td>
                  <td className="p-2 text-right font-mono">{p.contracts}</td>
                  <td className="p-2 text-right font-mono">{p.entry_price.toFixed(2)}</td>
                  <td className="p-2 text-right font-mono">{p.mark_price.toFixed(2)}</td>
                  <td
                    className={`p-2 text-right font-mono ${
                      p.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {p.unrealized_pnl.toFixed(2)}
                  </td>
                  <td className="p-2 text-right">{p.leverage}x</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">Order history</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-zinc-500">
              <tr>
                <th className="text-left p-2">When</th>
                <th className="text-left p-2">Symbol</th>
                <th className="text-left p-2">Side</th>
                <th className="text-right p-2">Qty</th>
                <th className="text-right p-2">Notional</th>
                <th className="text-right p-2">Entry</th>
                <th className="text-right p-2">PnL</th>
                <th className="text-left p-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {(orders.data ?? []).map((o) => (
                <tr key={o.id} className="border-t border-zinc-800">
                  <td className="p-2 text-zinc-400">{new Date(o.created_at).toLocaleString()}</td>
                  <td className="p-2 font-mono">{o.symbol}</td>
                  <td className="p-2">{o.side}</td>
                  <td className="p-2 text-right font-mono">{o.qty}</td>
                  <td className="p-2 text-right font-mono">${o.notional_usdt.toFixed(2)}</td>
                  <td className="p-2 text-right font-mono">{o.entry_price.toFixed(2)}</td>
                  <td
                    className={`p-2 text-right font-mono ${
                      o.realized_pnl_usdt >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {o.realized_pnl_usdt.toFixed(2)}
                  </td>
                  <td className="p-2">{o.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
