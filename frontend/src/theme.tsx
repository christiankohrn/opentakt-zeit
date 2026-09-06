import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "light" | "dark" | "system";
const KEY = "ze-theme";

function isDark(theme: Theme) {
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function apply(theme: Theme) {
  const dark = isDark(theme);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? "#000e1e" : "#004d9d");
}

type Ctx = { theme: Theme; dark: boolean; setTheme: (t: Theme) => void; cycle: () => void };

const ThemeContext = createContext<Ctx>({
  theme: "system",
  dark: false,
  setTheme: () => {},
  cycle: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    try {
      return (localStorage.getItem(KEY) as Theme) || "system";
    } catch {
      return "system";
    }
  });
  const [dark, setDark] = useState(false);

  useEffect(() => {
    apply(theme);
    setDark(isDark(theme));
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* ignore */
    }
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => {
      apply("system");
      setDark(mq.matches);
    };
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [theme]);

  const cycle = () => {
    setThemeState((t) => (t === "system" ? "light" : t === "light" ? "dark" : "system"));
  };

  return (
    <ThemeContext.Provider value={{ theme, dark, setTheme: setThemeState, cycle }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
