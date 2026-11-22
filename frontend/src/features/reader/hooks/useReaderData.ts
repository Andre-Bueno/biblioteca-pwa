import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../../shared/api-client';
import { getBook, useItem, type BookInfo, type Item } from '../../../shared/items';
import { getProgress } from '../../../shared/progress';
import { selectSource, type ReaderSource, type UnitPosition } from '../sources';

/** What the messages talk about: a book (EPUB) or a generic item (pages). */
export type ReaderSubject = 'book' | 'item';

export interface ReaderReady {
  status: 'ready';
  item: Item;
  source: ReaderSource;
  /** Book structure (title, chapters); `null` for items made of image pages. */
  book: BookInfo | null;
  /** Locator the server holds (`null` = never read), exactly as saved. */
  savedLocator: number | null;
  /** The saved locator decoded by the source codec and clamped to the units that exist. */
  savedPosition: UnitPosition;
}

export type ReaderData =
  | { status: 'loading' }
  | { status: 'notfound' | 'error'; subject: ReaderSubject }
  | { status: 'unsupported' }
  | ReaderReady;

type Loaded = Exclude<ReaderData, { status: 'loading' }>;
interface Settled {
  key: string;
  result: Loaded;
}

function subjectOf(item: Item): ReaderSubject {
  return item.type === 'book' ? 'book' : 'item';
}

/** Page items (manga) and books are readable today; PDF has no page endpoint yet. */
function isReadable(item: Item): boolean {
  return item.type === 'manga' || item.type === 'book';
}

async function loadReady(item: Item, signal: AbortSignal): Promise<ReaderReady> {
  const isBook = item.type === 'book';
  const [book, progress] = await Promise.all([
    isBook ? getBook(item.id, signal) : Promise.resolve(null),
    getProgress(item.id, signal),
  ]);
  const source = selectSource(item.type, { pageCount: item.page_count ?? 0, book });
  const savedLocator = progress ? progress.locator : null;
  const decoded = source.codec.decode(savedLocator);
  const unit = source.clampUnit(decoded.unit);
  return {
    status: 'ready',
    item,
    source,
    book,
    savedLocator,
    savedPosition: { unit, bp: unit === decoded.unit ? decoded.bp : 0 },
  };
}

/**
 * Single data hook of the reader: loads the item, the book structure when the item is a book and
 * the saved progress, and hands back the {@link ReaderSource} that fits the item type with the
 * saved position decoded by that source. A 404 means "not found"; any other failure is an error
 * that `retry` repeats. `data` is `loading` until the answer for the current item and attempt.
 */
export function useReaderData(itemId: string): { data: ReaderData; retry: () => void } {
  const { state, retry: retryItem } = useItem(itemId);
  const [retryToken, setRetryToken] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const item = state.status === 'ready' ? state.item : null;
  const key = item ? `${item.id}:${retryToken}` : '';

  useEffect(() => {
    if (!item || !isReadable(item)) return undefined;
    const controller = new AbortController();
    const { signal } = controller;
    loadReady(item, signal)
      .then((result) => {
        if (!signal.aborted) setSettled({ key, result });
      })
      .catch((error: unknown) => {
        if (signal.aborted) return;
        const notFound = error instanceof ApiError && error.status === 404;
        const status = notFound ? 'notfound' : 'error';
        setSettled({ key, result: { status, subject: subjectOf(item) } });
      });
    return () => controller.abort();
  }, [key, item]);

  // One retry mechanism: the token restarts the extras (book, progress). The item itself is only
  // reloaded when IT failed; reloading a good item would hand the effect a new object and load
  // everything twice.
  const itemFailed = state.status === 'notfound' || state.status === 'error';
  const retry = useCallback(() => {
    if (itemFailed) retryItem();
    setRetryToken((value) => value + 1);
  }, [itemFailed, retryItem]);

  let data: ReaderData = { status: 'loading' };
  if (state.status === 'notfound' || state.status === 'error') {
    data = { status: state.status, subject: 'item' };
  } else if (item && !isReadable(item)) {
    data = { status: 'unsupported' };
  } else if (item && settled?.key === key) {
    data = settled.result;
  }
  return { data, retry };
}
