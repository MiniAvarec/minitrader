import { useEffect, useState } from "react";
import { api } from "../api/client";

export function useLive() {
  const [last, setLast] = useState<any>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let ka: ReturnType<typeof setInterval> | null = null;
    let stopped = false;
    (async () => {
      try {
        const r = await api.get<{ token: string }>("/auth/ws-token");
        if (stopped) return;
        const proto = location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(
          `${proto}://${location.host}/ws/live?token=${encodeURIComponent(r.data.token)}`,
        );
        ws.onmessage = (e) => {
          try {
            setLast(JSON.parse(e.data));
          } catch {}
        };
        ka = setInterval(() => {
          try {
            ws?.send("ka");
          } catch {}
        }, 25_000);
      } catch {
        /* not authed yet */
      }
    })();
    return () => {
      stopped = true;
      if (ka) clearInterval(ka);
      ws?.close();
    };
  }, []);

  return last;
}
