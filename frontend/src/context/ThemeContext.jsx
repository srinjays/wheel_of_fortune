import { createContext, useMemo } from "react";
import { getTheme } from "../themes/themes";

export const ThemeContext = createContext({ theme: null });

export function ThemeProvider({ themeKey, children }) {
  const theme = useMemo(() => getTheme(themeKey), [themeKey]);
  const value = useMemo(() => ({ theme }), [theme]);

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}
