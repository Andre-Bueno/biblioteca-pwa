import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../../shared/api-client';
import { useVersion } from '../../../shared/system';

export type CheckResult =
  | { kind: 'none' }
  | { kind: 'latest' }
  | { kind: 'available'; tag: string }
  | { kind: 'rate-limited' }
  | { kind: 'error' };

const DEFAULT_BLOCK_S = 60;

/** Admin "Verificar atualizações": one request at a time; a 429 blocks the button for a while. */
export function useCheckUpdates() {
  const { check } = useVersion();
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [result, setResult] = useState<CheckResult>({ kind: 'none' });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);

  const run = useCallback(async () => {
    setBusy(true);
    setResult({ kind: 'none' });
    try {
      const info = await check();
      if (!alive.current) return;
      setResult(
        info.update_available && info.latest
          ? { kind: 'available', tag: info.latest.tag }
          : { kind: 'latest' },
      );
    } catch (error) {
      if (!alive.current) return;
      if (error instanceof ApiError && error.status === 429) {
        setResult({ kind: 'rate-limited' });
        setBlocked(true);
        const seconds = error.retryAfterSeconds ?? DEFAULT_BLOCK_S;
        timer.current = setTimeout(() => setBlocked(false), seconds * 1000);
      } else {
        setResult({ kind: 'error' });
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  }, [check]);

  return { busy, blocked, result, run };
}
