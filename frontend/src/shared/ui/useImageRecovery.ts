import { useCallback, useState } from 'react';
import { apiClient } from '../api-client';

export type ImageState = 'loading' | 'loaded' | 'failed';

// An <img> error carries no HTTP status. We only suspect the SESSION (expired access cookie)
// when no image loaded recently; if some other image just loaded, this one is a 404/422/etc.
const RECENT_SUCCESS_MS = 30_000;
// At most one session recovery per window, shared by every image on the screen.
const RECOVERY_WINDOW_MS = 60_000;

let lastLoadAt = -Infinity;
let lastRecoveryAt = -Infinity;
let recovery: Promise<boolean> | null = null;

/** Resolves true when the session was refreshed and the image is worth loading again. */
function recoverSession(): Promise<boolean> {
  const now = Date.now();
  if (recovery) return recovery; // concurrent failures share the attempt
  if (now - lastLoadAt < RECENT_SUCCESS_MS) return Promise.resolve(false);
  if (now - lastRecoveryAt < RECOVERY_WINDOW_MS) return Promise.resolve(false);
  lastRecoveryAt = now;
  recovery = apiClient
    .refreshSession()
    .catch(() => false)
    .finally(() => {
      recovery = null;
    });
  return recovery;
}

/** Test hook: forget the shared recovery state. */
export function resetImageRecovery(): void {
  lastLoadAt = -Infinity;
  lastRecoveryAt = -Infinity;
  recovery = null;
}

/**
 * On the first error, and only when it may be a session problem, refresh the session once (shared
 * across images) and remount the image. Otherwise the image goes straight to "failed" with a
 * manual retry.
 */
export function useImageRecovery() {
  const [state, setState] = useState<ImageState>('loading');
  const [attempt, setAttempt] = useState(0);

  const onLoad = useCallback(() => {
    lastLoadAt = Date.now();
    setState('loaded');
  }, []);
  const onError = useCallback(() => {
    if (attempt > 0) {
      setState('failed');
      return;
    }
    void recoverSession().then((retry) => {
      if (retry) {
        setState('loading');
        setAttempt(1);
      } else {
        setState('failed');
      }
    });
  }, [attempt]);
  const retry = useCallback(() => {
    setState('loading');
    setAttempt((value) => value + 1);
  }, []);

  return { state, attempt, onLoad, onError, retry };
}
