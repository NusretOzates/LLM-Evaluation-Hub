import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type ThemePreference = "system" | "light" | "dark";
const ThemeContext = createContext<{
  preference: ThemePreference;
  resolvedTheme: "light" | "dark";
  setPreference: (value: ThemePreference) => void;
}>({ preference: "system", resolvedTheme: "light", setPreference: () => {} });
function storedPreference(): ThemePreference {
  try {
    const value = localStorage.getItem("evaluation-hub.theme");
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(() =>
    typeof window === "undefined" ? "system" : storedPreference(),
  );
  const [systemDark, setSystemDark] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const resolvedTheme = preference === "system" ? (systemDark ? "dark" : "light") : preference;
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(media.matches);
    media.addEventListener("change", update);
    update();
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.style.colorScheme = resolvedTheme;
    try {
      localStorage.setItem("evaluation-hub.theme", preference);
    } catch {
      /* Use the in-memory preference. */
    }
  }, [preference, resolvedTheme]);
  return <ThemeContext.Provider value={{ preference, resolvedTheme, setPreference }}>{children}</ThemeContext.Provider>;
}
export const useTheme = () => useContext(ThemeContext);
