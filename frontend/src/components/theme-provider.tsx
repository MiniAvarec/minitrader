import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Theme = "dark" | "light" | "system";

type ThemeProviderState = {
  theme: Theme;
  resolved: "dark" | "light";
  setTheme: (theme: Theme) => void;
};

const initialState: ThemeProviderState = {
  theme: "dark",
  resolved: "dark",
  setTheme: () => null,
};

const ThemeProviderContext = createContext<ThemeProviderState>(initialState);

function readSystem(): "dark" | "light" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({
  children,
  defaultTheme = "dark",
  storageKey = "mt-theme",
}: {
  children: ReactNode;
  defaultTheme?: Theme;
  storageKey?: string;
}) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return defaultTheme;
    return (localStorage.getItem(storageKey) as Theme | null) || defaultTheme;
  });
  const [resolved, setResolved] = useState<"dark" | "light">(() =>
    theme === "system" ? readSystem() : (theme as "dark" | "light"),
  );

  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const next = theme === "system" ? readSystem() : (theme as "dark" | "light");
      root.classList.remove("light", "dark");
      root.classList.add(next);
      setResolved(next);
    };
    apply();
    if (theme === "system") {
      const m = window.matchMedia("(prefers-color-scheme: dark)");
      m.addEventListener("change", apply);
      return () => m.removeEventListener("change", apply);
    }
  }, [theme]);

  function setTheme(t: Theme) {
    localStorage.setItem(storageKey, t);
    setThemeState(t);
  }

  return (
    <ThemeProviderContext.Provider value={{ theme, resolved, setTheme }}>
      {children}
    </ThemeProviderContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeProviderContext);
