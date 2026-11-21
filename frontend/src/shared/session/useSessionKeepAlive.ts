import { useEffect } from 'react';
import { apiClient } from '../api-client';

const INTERVAL_MS = 10 * 60 * 1000; // access token lives ~15 min
const MIN_GAP_MS = 5 * 60 * 1000;

/**
 * Images (covers, pages) are loaded by <img>, which cannot recover from a 401 by itself.
 * Rotating the session proactively keeps the access cookie fresh while the app is in use.
 */
export function useSessionKeepAlive(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    let last = Date.now();
    const refresh = () => {
      last = Date.now();
      apiClient.refreshSession().catch(() => undefined); // transient errors: next tick retries
    };
    const timer = setInterval(refresh, INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() - last > MIN_GAP_MS) refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [active]);
}
