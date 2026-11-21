import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../../shared/api-client';
import { getEnrichStatus, startEnrich, type EnrichStatus } from '../../../shared/series';

export const POLL_INTERVAL_MS = 2000;
export const MAX_POLLS = 150; // about 5 minutes; then the UI lets go (the server keeps working)
const MAX_POLL_FAILURES = 3;

export type EnrichPhase =
  'idle' | 'running' | 'finished' | 'failed' | 'forbidden' | 'rate-limited' | 'error' | 'gave-up';

export interface EnrichView {
  phase: EnrichPhase;
  status: EnrichStatus | null;
}

/**
 * "Atualizar metadados" (admin): POST then a light poll of the status. Everything stops on
 * unmount (AbortController + timers) and at MAX_POLLS. Never blocks navigation.
 */
export function useEnrich(onFinished?: () => void) {
  const [view, setView] = useState<EnrichView>({ phase: 'idle', status: null });
  const abort = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finishedCallback = useRef(onFinished);

  useEffect(() => {
    finishedCallback.current = onFinished;
  });

  const stop = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => stop, [stop]);

  const sleep = useCallback(
    (signal: AbortSignal) =>
      new Promise<void>((resolve) => {
        timer.current = setTimeout(resolve, POLL_INTERVAL_MS);
        signal.addEventListener('abort', () => resolve(), { once: true });
      }),
    [],
  );

  /** Sequential loop (no overlapping requests); ends on a final state, MAX_POLLS or abort. */
  const follow = useCallback(
    async (controller: AbortController) => {
      const { signal } = controller;
      let failures = 0;
      for (let count = 0; count < MAX_POLLS; count += 1) {
        await sleep(signal);
        if (signal.aborted) return;
        try {
          const status = await getEnrichStatus(signal);
          if (signal.aborted) return;
          failures = 0;
          if (status.state === 'running') {
            setView({ phase: 'running', status });
            continue;
          }
          if (status.state === 'failed') {
            setView({ phase: 'failed', status });
          } else {
            setView({ phase: 'finished', status });
            finishedCallback.current?.();
          }
          return;
        } catch {
          if (signal.aborted) return;
          failures += 1;
          if (failures >= MAX_POLL_FAILURES) {
            setView({ phase: 'error', status: null });
            return;
          }
        }
      }
      setView((previous) => ({ phase: 'gave-up', status: previous.status }));
    },
    [sleep],
  );

  const start = useCallback(async () => {
    if (abort.current) return; // already starting/running: the button is disabled anyway
    const controller = new AbortController();
    abort.current = controller;
    setView({ phase: 'running', status: null });
    try {
      await startEnrich();
    } catch (error) {
      if (controller.signal.aborted) return;
      // 409 = already running on the server: just follow it.
      if (!(error instanceof ApiError && error.status === 409)) {
        abort.current = null;
        const code = error instanceof ApiError ? error.status : 0;
        setView({
          phase: code === 403 ? 'forbidden' : code === 429 ? 'rate-limited' : 'error',
          status: null,
        });
        return;
      }
    }
    if (controller.signal.aborted) return;
    await follow(controller);
  }, [follow]);

  // Allow a new run once the previous one is over.
  const running = view.phase === 'running';
  useEffect(() => {
    if (!running && abort.current) {
      abort.current.abort();
      abort.current = null;
    }
  }, [running]);

  return { ...view, running, start };
}
