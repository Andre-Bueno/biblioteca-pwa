import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ThemeContext, type ThemePreference } from './theme-context';
import { useSystemTheme } from './useSystemTheme';

/** Preference lives in memory for now; persisting it on the server comes later. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>('system');
  const system = useSystemTheme();
  const resolved = preference === 'system' ? system : preference;

  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
  }, [resolved]);

  const value = useMemo(() => ({ preference, resolved, setPreference }), [preference, resolved]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
