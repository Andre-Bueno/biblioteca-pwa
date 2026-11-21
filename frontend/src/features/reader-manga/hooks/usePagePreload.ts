import { useEffect, useRef } from 'react';
import { pageUrl } from '../../../shared/items';

export const PRELOAD_AHEAD = 2;
/** Pages behind the current one that stay referenced (back-navigation). */
export const KEEP_BEHIND = 2;
export const MAX_PRELOADED = 8;

/**
 * Warms the browser cache with the next pages (reading order) while the current one is shown.
 * The references kept here only stop the images from being collected mid-load, so they are
 * bounded: anything behind `page - 2` or beyond the lookahead is dropped, and the map never
 * holds more than MAX_PRELOADED entries.
 */
export function usePagePreload(
  itemId: string,
  page: number,
  pageCount: number,
  enabled: boolean,
): void {
  const loaded = useRef(new Map<number, HTMLImageElement>());

  useEffect(() => {
    const cache = loaded.current;
    cache.clear(); // new item: forget the previous one
    return () => cache.clear();
  }, [itemId]);

  useEffect(() => {
    if (!enabled) return;
    const cache = loaded.current;
    for (let step = 1; step <= PRELOAD_AHEAD; step += 1) {
      const index = page + step;
      if (index >= pageCount) break;
      if (cache.has(index)) continue;
      const image = new Image();
      image.decoding = 'async';
      image.src = pageUrl(itemId, index);
      cache.set(index, image);
    }
    for (const index of [...cache.keys()]) {
      if (index < page - KEEP_BEHIND || index > page + PRELOAD_AHEAD) cache.delete(index);
    }
    while (cache.size > MAX_PRELOADED) {
      const oldest = cache.keys().next().value;
      if (oldest === undefined) break;
      cache.delete(oldest);
    }
  }, [itemId, page, pageCount, enabled]);
}
