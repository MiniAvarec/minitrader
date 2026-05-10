import Chart from "../components/Chart";
import NewsPanel from "../components/NewsPanel";
import SignalFeed from "../components/SignalFeed";
import { useLive } from "../lib/useLive";

export default function Dashboard() {
  const live = useLive();
  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-8 flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-4">
          <Chart symbol="BTCUSDT" />
          <Chart symbol="ETHUSDT" />
        </div>
        <div>
          <h2 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">Signals</h2>
          <SignalFeed live={live} />
        </div>
      </div>
      <div className="col-span-4">
        <h2 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">News</h2>
        <NewsPanel />
      </div>
    </div>
  );
}
