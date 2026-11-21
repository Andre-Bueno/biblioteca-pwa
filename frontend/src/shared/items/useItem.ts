import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api-client';
import { getItem } from './api';
import type { Item } from './types';

export type ItemState =
  | { status: 'loading' }
  | { status: 'notfound' }
  | { status: 'error' }
  | { status: 'ready'; item: Item };

interface Settled {
  key: string;
  result: Exclude<ItemState, { status: 'loading' }>;
}

/**
 * Loads one item (`GET /items/{id}`). The answer is stored with the key it belongs to, so a late
 * answer for another item is never shown; while a new id loads the state is `loading`.
 */
export function useItem(itemId: string): { state: ItemState; retry: () => void } {
  const [retryToken, setRetryToken] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const key = `${itemId}:${retryToken}`;

  useEffect(() => {
    const controller = new AbortController();
    getItem(itemId, controller.signal)
      .then((item) => {
        if (!controller.signal.aborted) setSettled({ key, result: { status: 'ready', item } });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const notFound = error instanceof ApiError && error.status === 404;
        setSettled({ key, result: { status: notFound ? 'notfound' : 'error' } });
      });
    return () => controller.abort();
  }, [key, itemId]);

  const retry = useCallback(() => setRetryToken((value) => value + 1), []);
  const state: ItemState = settled?.key === key ? settled.result : { status: 'loading' };
  return { state, retry };
}
