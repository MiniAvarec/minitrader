import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Search } from "lucide-react";
import {
  addWatchlist,
  ExchangeInfo,
  getExchanges,
  Instrument,
  searchInstruments,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function AddPairDialog() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [exchange, setExchange] = useState<string>("binance");
  const [search, setSearch] = useState("");
  // IBKR manual-entry: users can add non-universe contracts by typing a
  // dot-encoded symbol directly (e.g. NFLX.SMART.USD, ES.CME.USD.202509).
  const [ibkrManual, setIbkrManual] = useState("");

  const { data: exchanges = [] } = useQuery<ExchangeInfo[]>({
    queryKey: ["exchanges"],
    queryFn: getExchanges,
  });

  const { data: instruments = [], isFetching } = useQuery<Instrument[]>({
    queryKey: ["instruments", exchange, search],
    queryFn: () => searchInstruments(exchange, search, 25),
    enabled: open,
  });

  const add = useMutation({
    mutationFn: ({ exchange, symbol }: { exchange: string; symbol: string }) =>
      addWatchlist(exchange, symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="gap-1.5">
          <Plus className="h-3.5 w-3.5" /> Add pair
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add a trading pair</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <Select value={exchange} onValueChange={setExchange}>
            <SelectTrigger>
              <SelectValue placeholder="Exchange" />
            </SelectTrigger>
            <SelectContent>
              {exchanges.map((e) => (
                <SelectItem key={e.id} value={e.id}>
                  {e.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              autoFocus
              placeholder="Search symbol (e.g. SOL)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-7"
            />
          </div>
          {exchange === "ibkr" && (
            <div className="flex flex-col gap-1.5 rounded-md border border-dashed border-border p-3">
              <span className="text-xs font-medium">
                Or add a contract manually
              </span>
              <span className="text-[10px] text-muted-foreground">
                Format: <code>ROOT.ROUTING.CURRENCY[.expiry][.right.strike]</code>
                . e.g. <code>NFLX.SMART.USD</code>, <code>ES.CME.USD.202509</code>.
              </span>
              <div className="flex gap-2">
                <Input
                  value={ibkrManual}
                  onChange={(e) => setIbkrManual(e.target.value.toUpperCase())}
                  placeholder="AAPL.SMART.USD"
                  className="font-mono"
                />
                <Button
                  size="sm"
                  disabled={!ibkrManual || !ibkrManual.includes(".")}
                  onClick={() => {
                    add.mutate({ exchange: "ibkr", symbol: ibkrManual });
                    setIbkrManual("");
                    setOpen(false);
                  }}
                >
                  Add
                </Button>
              </div>
            </div>
          )}
          <div className="max-h-72 overflow-auto rounded border">
            {isFetching && (
              <div className="flex items-center justify-center p-4 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            )}
            {!isFetching && instruments.length === 0 && (
              <div className="p-4 text-center text-xs text-muted-foreground">
                No instruments found.
              </div>
            )}
            {instruments.map((i) => (
              <button
                key={`${i.exchange}:${i.symbol}`}
                className="flex w-full items-center justify-between border-b px-3 py-2 text-left text-sm last:border-b-0 hover:bg-muted/30"
                onClick={() => {
                  add.mutate({ exchange: i.exchange, symbol: i.symbol });
                  setOpen(false);
                }}
              >
                <span className="font-mono">{i.symbol}</span>
                <span className="text-[10px] text-muted-foreground">
                  tick {i.tick_size} · lot {i.lot_size}
                </span>
              </button>
            ))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
