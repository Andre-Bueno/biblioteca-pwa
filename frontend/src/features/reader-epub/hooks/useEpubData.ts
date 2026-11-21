import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../../shared/api-client';
import { getBook, type BookInfo, type Item, type ItemState } from '../../../shared/items';
import { getProgress } from '../../../shared/progress';

export type EpubData =
  | { status: 'loading' }
  | { status: 'notfound' }
  | { status: 'error' }
  | {
      status: 'ready';
      item: Item;
      book: BookInfo;
      /** Locator the server holds (null = never read). */
      savedLocator: number | null;
    };

interface Settled {
  key: string;
  result: Exclude<EpubData, { status: 'loading' }>;
}

/**
 * Combines the item (loaded by the reader route) with the book structure and the saved progress
 * (404 on progress = start at the beginning). A 404 on the book itself means "not found".
 */
export function useEpubData(
  itemState: ItemState,
  retryItem: () => void,
): { data: EpubData; retry: () => void } {
  const [retryToken, setRetryToken] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const item = itemState.status === 'ready' ? itemState.item : null;
  const key = item ? `${item.id}:${retryToken}` : '';

  useEffect(() => {
    if (!item) return undefined;
    const controller = new AbortController();
    const { signal } = controller;
    Promise.all([getBook(item.id, signal), getProgress(item.id, signal)])
      .then(([book, progress]) => {
        if (signal.aborted) return;
        const savedLocator = progress ? progress.locator : null;
        setSettled({ key, result: { status: 'ready', item, book, savedLocator } });
      })
      .catch((error: unknown) => {
        if (signal.aborted) return;
        const notFound = error instanceof ApiError && error.status === 404;
        setSettled({ key, result: { status: notFound ? 'notfound' : 'error' } });
      });
    return () => controller.abort();
  }, [key, item]);

  const retry = useCallback(() => {
    setRetryToken((value) => value + 1);
    retryItem();
  }, [retryItem]);

  let data: EpubData = { status: 'loading' };
  if (itemState.status === 'notfound' || itemState.status === 'error') {
    data = { status: itemState.status };
  } else if (item && settled?.key === key) {
    data = settled.result;
  }
  return { data, retry };
}
