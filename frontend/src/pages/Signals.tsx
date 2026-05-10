import SignalFeed from "../components/SignalFeed";
import { useLive } from "../lib/useLive";

export default function Signals() {
  const live = useLive();
  return (
    <div className="max-w-5xl">
      <h2 className="text-sm uppercase tracking-wide text-zinc-400 mb-2">Signals</h2>
      <SignalFeed live={live} />
    </div>
  );
}
