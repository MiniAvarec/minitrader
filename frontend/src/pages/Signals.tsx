import SignalFeed from "@/components/SignalFeed";
import { useLive } from "@/lib/useLive";

export default function Signals() {
  const live = useLive();
  return (
    <div className="flex flex-col gap-3 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-mono uppercase tracking-wider">Signal Feed</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Live signals from your active strategies — last 50.
          </p>
        </div>
      </div>
      <SignalFeed live={live} />
    </div>
  );
}
