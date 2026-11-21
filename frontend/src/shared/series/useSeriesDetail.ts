import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api-client';
import { getSeries } from './api';
import type { SeriesDetail } from './types';

export type SeriesDetailState =
  | { status: 'loading' }
  | { status: 'notfound' }
  | { status: 'error' }
  | { status: 'ready'; series: SeriesDetail };

interface Settled {
  key: string;
  result: Exclude<SeriesDetailState, { status: 'loading' }>;
}

/**
 * Loads one series. The answer is stored with the key it belongs to, so a late answer for another
 * series (or an older retry) is never shown. `seriesId` null means "no series": nothing is loaded.
 * `reload` refetches in the background: the current detail stays on screen until the new one
 * arrives (a failed background reload keeps the old detail).
 */
export function useSeriesDetail(seriesId: string | null): {
  state: SeriesDetailState;
  retry: () => void;
  reload: () => void;
} {
  const [retryToken, setRetryToken] = useState(0);
  const [reloadToken, setReloadToken] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const key = `${seriesId ?? ''}:${retryToken}`;

  useEffect(() => {
    if (!seriesId) return undefined;
    const controller = new AbortController();
    getSeries(seriesId, controller.signal)
      .then((series) => {
        if (controller.signal.aborted) return;
        setSettled({ key, result: { status: 'ready', series } });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const notFound = error instanceof ApiError && error.status === 404;
        setSettled((previous) =>
          reloadToken > 0 && previous?.key === key && previous.result.status === 'ready'
            ? previous
            : { key, result: { status: notFound ? 'notfound' : 'error' } },
        );
      });
    return () => controller.abort();
  }, [key, seriesId, reloadToken]);

  const retry = useCallback(() => setRetryToken((value) => value + 1), []);
  const reload = useCallback(() => setReloadToken((value) => value + 1), []);
  const state: SeriesDetailState =
    seriesId && settled?.key === key ? settled.result : { status: 'loading' };
  return { state, retry, reload };
}
