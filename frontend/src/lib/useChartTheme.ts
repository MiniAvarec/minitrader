import { useEffect, useState } from "react";

export type ChartTheme = {
  background: string;
  foreground: string;
  muted: string;
  border: string;
  success: string;
  destructive: string;
  primary: string;
  accent: string;
};

// lightweight-charts v4 only understands hex, rgb(), rgba(), and named colors —
// it cannot parse hsl() in any syntax. We round-trip every value through a
// detached element so the browser hands us back the canonical rgb(...) form.
function resolve(varName: string): string {
  if (typeof document === "undefined") return "rgb(0, 0, 0)";
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
  if (!raw) return "rgb(0, 0, 0)";
  const tmp = document.createElement("div");
  tmp.style.color = `hsl(${raw})`;
  document.body.appendChild(tmp);
  const computed = getComputedStyle(tmp).color || "rgb(0, 0, 0)";
  document.body.removeChild(tmp);
  return computed;
}

function snapshot(): ChartTheme {
  return {
    background: resolve("--background"),
    foreground: resolve("--foreground"),
    muted: resolve("--muted-foreground"),
    border: resolve("--border"),
    success: resolve("--success"),
    destructive: resolve("--destructive"),
    primary: resolve("--primary"),
    accent: resolve("--accent"),
  };
}

export function useChartTheme(): ChartTheme {
  const [t, setT] = useState<ChartTheme>(() => snapshot());

  useEffect(() => {
    setT(snapshot());
    const obs = new MutationObserver(() => setT(snapshot()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  return t;
}
