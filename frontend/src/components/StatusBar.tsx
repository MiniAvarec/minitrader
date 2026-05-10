import { useEffect, useState } from "react";
import { useAuth } from "@/auth";
import { cn } from "@/lib/utils";

export function StatusBar() {
  const { me } = useAuth();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const auto = me?.mode === "auto_execute";
  const hh = now.toLocaleTimeString("en-GB", { hour12: false });

  return (
    <footer className="flex h-7 items-center justify-between border-t border-border bg-card px-3 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
          LIVE
        </span>
        <span className="hidden sm:inline">SESSION {me?.email ?? "—"}</span>
      </div>
      <div className="flex items-center gap-4">
        <span className={cn(auto ? "text-destructive" : "text-success")}>
          {auto ? "AUTO-EXEC" : "SIGNAL-ONLY"}
        </span>
        <span className="tabular text-foreground">{hh} UTC</span>
      </div>
    </footer>
  );
}
