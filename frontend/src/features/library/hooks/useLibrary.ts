import { useCallback, useEffect, useState } from 'react';
import { useDebouncedValue } from '../../../shared/hooks';
import { listSeries, type SeriesSummary } from '../../../shared/series';

export const PAGE_SIZE = 30;
export const SEARCH_DEBOUNCE_MS = 350;

export type LibraryStatus = 'loading' | 'ready' | 'error';

interface Loaded {
  key: string;
  items: SeriesSummary[];
  hasMore: boolean;
}

/**
 * Series listing: debounced search and "load more" by offset. The loaded page is stored together
 * with the query key it answers, so a stale answer can never be shown for a newer query and no
 * state has to be reset synchronously.
 */
export function useLibrary() {
  const [query, setQuery] = useState('');
  const [retryToken, setRetryToken] = useState(0);
  const debouncedQuery = useDebouncedValue(query.trim(), SEARCH_DEBOUNCE_MS);

  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);

  const key = JSON.stringify([debouncedQuery, retryToken]);
  const paramQ = debouncedQuery || undefined;

  useEffect(() => {
    const controller = new AbortController();
    listSeries({ q: paramQ, limit: PAGE_SIZE }, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return; // superseded: never overwrite the newer answer
        setLoaded({ key, items: data.items, hasMore: data.has_more });
        setFailedKey(null);
        setMoreFailed(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailedKey(key);
      });
    return () => controller.abort();
  }, [key, paramQ]);

  const current = loaded?.key === key ? loaded : null;
  const status: LibraryStatus = current ? 'ready' : failedKey === key ? 'error' : 'loading';

  const loadMore = useCallback(async () => {
    if (!current || !current.hasMore || loadingMore) return;
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const data = await listSeries({ q: paramQ, limit: PAGE_SIZE, offset: current.items.length });
      setLoaded((previous) => {
        if (!previous || previous.key !== key) return previous; // the query changed meanwhile
        const known = new Set(previous.items.map((item) => item.id));
        const fresh = data.items.filter((item) => !known.has(item.id));
        return { ...previous, items: [...previous.items, ...fresh], hasMore: data.has_more };
      });
    } catch {
      setMoreFailed(true);
    } finally {
      setLoadingMore(false);
    }
  }, [current, loadingMore, paramQ, key]);

  const retry = useCallback(() => setRetryToken((value) => value + 1), []);

  return {
    query,
    setQuery,
    status,
    items: current?.items ?? [],
    hasMore: current?.hasMore ?? false,
    loadingMore,
    moreFailed,
    loadMore,
    retry,
    filtering: debouncedQuery !== '',
  };
}
