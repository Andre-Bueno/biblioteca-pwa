import { useCallback, useEffect, useRef, useState } from 'react';
import { putProgress } from './api';
import { createProgressSaver, type ProgressSaver } from './progress-saver';
import type { SaveStatus } from './types';

export interface UseProgressSaver {
  /** Call whenever the reader lands on a (new) locator. */
  report: (locator: number) => void;
  /** Call once with the server-known locator so it is not re-sent. */
  setBaseline: (locator: number | null) => void;
  status: SaveStatus;
}

/**
 * Saves reading progress with a debounce and flushes it (fetch keepalive through the api-client,
 * never sendBeacon) when the page is hidden, hidden-by-navigation, or the reader unmounts.
 */
export function useProgressSaver(itemId: string): UseProgressSaver {
  const [status, setStatus] = useState<SaveStatus>('idle');
  const saverRef = useRef<ProgressSaver | null>(null);

  useEffect(() => {
    const saver = createProgressSaver({
      save: (locator, { keepalive }) => putProgress(itemId, locator, { keepalive }),
      onStatus: setStatus,
    });
    saverRef.current = saver;

    const onVisibility = () => {
      if (document.visibilityState === 'hidden') void saver.flush(true);
    };
    const onPageHide = () => void saver.flush(true);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', onPageHide);
      void saver.flush(true); // leaving the reader: send what is pending
      saver.dispose();
      saverRef.current = null;
    };
  }, [itemId]);

  const report = useCallback((locator: number) => saverRef.current?.report(locator), []);
  const setBaseline = useCallback(
    (locator: number | null) => saverRef.current?.setBaseline(locator),
    [],
  );

  return { report, setBaseline, status };
}
