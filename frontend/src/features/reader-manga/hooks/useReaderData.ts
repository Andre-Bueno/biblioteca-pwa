import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../../shared/api-client';
import { getItem, type Item } from '../../../shared/items';
import { getProgress } from '../../../shared/progress';

export type ReaderData =
  | { status: 'loading' }
  | { status: 'notfound' }
  | { status: 'error' }
  | {
      status: 'ready';
      item: Item;
      /** Locator the server holds (null = never read): the reader resumes there. */
      savedLocator: number | null;
    };

interface Settled {
  key: string;
  result: Exclude<ReaderData, { status: 'loading' }>;
}

/** Loads the item and the saved progress (404 = start at page 0) before the reader mounts. */
export function useReaderData(itemId: string): { data: ReaderData; retry: () => void } {
  const [retryToken, setRetryToken] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const key = `${itemId}:${retryToken}`;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getItem(itemId, controller.signal), getProgress(itemId, controller.signal)])
      .then(([item, progress]) =>
        setSettled({
          key,
          result: { status: 'ready', item, savedLocator: progress ? progress.locator : null },
        }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const notFound = error instanceof ApiError && error.status === 404;
        setSettled({ key, result: { status: notFound ? 'notfound' : 'error' } });
      });
    return () => controller.abort();
  }, [key, itemId]);

  const retry = useCallback(() => setRetryToken((value) => value + 1), []);
  const data: ReaderData = settled?.key === key ? settled.result : { status: 'loading' };
  return { data, retry };
}
