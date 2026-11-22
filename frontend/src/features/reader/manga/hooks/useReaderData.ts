import { useCallback, useEffect, useState } from 'react';
import type { Item, ItemState } from '../../../../shared/items';
import { getProgress } from '../../../../shared/progress';

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
  result: { status: 'ready'; item: Item; savedLocator: number | null } | { status: 'error' };
}

/**
 * Combines the item (loaded by the route, which also picks manga or book) with the saved
 * progress (404 = start at page 0) before the reader mounts.
 */
export function useReaderData(
  itemState: ItemState,
  retryItem: () => void,
): { data: ReaderData; retry: () => void } {
  const [retryToken, setRetryToken] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const item = itemState.status === 'ready' ? itemState.item : null;
  const key = item ? `${item.id}:${retryToken}` : '';

  useEffect(() => {
    if (!item) return undefined;
    const controller = new AbortController();
    getProgress(item.id, controller.signal)
      .then((progress) => {
        if (controller.signal.aborted) return;
        setSettled({
          key,
          result: { status: 'ready', item, savedLocator: progress ? progress.locator : null },
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setSettled({ key, result: { status: 'error' } });
      });
    return () => controller.abort();
  }, [key, item]);

  const retry = useCallback(() => {
    setRetryToken((value) => value + 1);
    retryItem();
  }, [retryItem]);

  let data: ReaderData = { status: 'loading' };
  if (itemState.status === 'notfound' || itemState.status === 'error') {
    data = { status: itemState.status };
  } else if (item && settled?.key === key) {
    data = settled.result;
  }
  return { data, retry };
}
