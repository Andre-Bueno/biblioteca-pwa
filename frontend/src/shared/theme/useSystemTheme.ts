import { useEffect, useState } from 'react';
import type { ResolvedTheme } from './theme-context';

const QUERY = '(prefers-color-scheme: dark)';

function current(): ResolvedTheme {
  return typeof window.matchMedia === 'function' && window.matchMedia(QUERY).matches
    ? 'dark'
    : 'light';
}

export function useSystemTheme(): ResolvedTheme {
  const [theme, setTheme] = useState<ResolvedTheme>(current);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia(QUERY);
    const onChange = () => setTheme(media.matches ? 'dark' : 'light');
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  return theme;
}
