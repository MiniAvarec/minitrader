import { useQuery } from "@tanstack/react-query";
import { AlertCircle, TrendingDown, TrendingUp } from "lucide-react";
import { api, OrderRow } from "@/api/client";
import PairBadge from "@/components/PairBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type PositionRow = {
  symbol: string;
  side: string;
  contracts: number;
  notional: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  leverage: number;
};

type ExchangeBlock = {
  exchange: string;
  usdt_balance: number;
  positions: PositionRow[];
};

type LivePositions = {
  exchanges: ExchangeBlock[];
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

  const blocks = positions.data?.exchanges ?? [];
  const orderRows = orders.data ?? [];

  return (
    <div className="flex flex-col gap-4 max-w-7xl">
      {blocks.length === 0 && !positions.error && (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground text-center">
            Add an API key for at least one exchange in Settings to see positions.
          </CardContent>
        </Card>
      )}
      {positions.error && (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" />
            Could not fetch positions — check your API keys.
          </CardContent>
        </Card>
      )}
      {blocks.map((b) => (
        <Card key={b.exchange}>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="font-mono uppercase tracking-wider">
                {b.exchange} · Positions
              </CardTitle>
              <div className="text-xs text-muted-foreground num mt-0.5">
                Balance ${b.usdt_balance.toFixed(2)} USDT
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {b.positions.length === 0 ? (
              <div className="p-6 text-center text-sm text-muted-foreground">
                No open positions.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Side</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Entry</TableHead>
                    <TableHead className="text-right">Mark</TableHead>
                    <TableHead className="text-right">uPnL</TableHead>
                    <TableHead className="text-right">Lev</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {b.positions.map((p, i) => {
                    const up = p.unrealized_pnl >= 0;
                    return (
                      <TableRow key={i}>
                        <TableCell className="font-mono font-semibold">
                          {p.symbol}
                        </TableCell>
                        <TableCell className="uppercase">
                          <Badge
                            variant={
                              p.side.toLowerCase() === "long" ||
                              p.side.toLowerCase() === "buy"
                                ? "success"
                                : "destructive"
                            }
                          >
                            {p.side}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right num">{p.contracts}</TableCell>
                        <TableCell className="text-right num">
                          {p.entry_price.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right num">
                          {p.mark_price.toFixed(2)}
                        </TableCell>
                        <TableCell
                          className={cn(
                            "text-right num inline-flex items-center justify-end gap-1 w-full",
                            up ? "text-success" : "text-destructive",
                          )}
                        >
                          {up ? (
                            <TrendingUp className="h-3 w-3" />
                          ) : (
                            <TrendingDown className="h-3 w-3" />
                          )}
                          {p.unrealized_pnl.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right num">{p.leverage}x</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="font-mono uppercase tracking-wider">
            Order history
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {orderRows.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              No orders yet.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Pair</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Notional</TableHead>
                  <TableHead className="text-right">Entry</TableHead>
                  <TableHead className="text-right">PnL</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orderRows.map((o) => {
                  const up = o.realized_pnl_usdt >= 0;
                  return (
                    <TableRow key={o.id}>
                      <TableCell className="text-muted-foreground text-xs num">
                        {new Date(o.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <PairBadge exchange={o.exchange} symbol={o.symbol} />
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={o.side === "buy" ? "success" : "destructive"}
                        >
                          {o.side.toUpperCase()}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right num">{o.qty}</TableCell>
                      <TableCell className="text-right num">
                        ${o.notional_usdt.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right num">
                        {o.entry_price.toFixed(2)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right num",
                          up ? "text-success" : "text-destructive",
                        )}
                      >
                        {o.realized_pnl_usdt.toFixed(2)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="muted">{o.status}</Badge>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
