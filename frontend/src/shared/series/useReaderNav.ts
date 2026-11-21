import { useSearchParams } from 'react-router-dom';
import { readerPath, seriesPath, type Item } from '../items';
import { chapterNeighbours } from './types';
import { useSeriesDetail } from './useSeriesDetail';

export interface ReaderNav {
  /** Where "back" goes: the series page when the chapter belongs to one, else the library. */
  backTo: string;
  backLabel: string;
  previous: { to: string; title: string } | null;
  next: { to: string; title: string } | null;
  /** True once the series order is known (so "last chapter" can be told apart from "unknown"). */
  seriesLoaded: boolean;
}

/**
 * Series context of the open chapter. Decision: the series id comes from `?serie=` (set by every
 * link the app builds) and falls back to `item.series_id` when the backend exposes it. The order
 * comes from `GET /series/{id}`, fetched once per series (the page stays mounted between chapters).
 * If the series cannot be loaded the reader keeps working, just without previous/next chapter.
 */
export function useReaderNav(item: Item | null): ReaderNav {
  const [params] = useSearchParams();
  const fromUrl = params.get('serie');
  const seriesId = fromUrl || item?.series_id || null;
  const { state } = useSeriesDetail(seriesId);

  const backToSeries = seriesId !== null && state.status !== 'notfound';
  const nav: ReaderNav = {
    backTo: backToSeries ? seriesPath(seriesId) : '/',
    backLabel: backToSeries ? 'Voltar para a série' : 'Voltar para a biblioteca',
    previous: null,
    next: null,
    seriesLoaded: false,
  };
  if (seriesId && item && state.status === 'ready') {
    const { previous, next } = chapterNeighbours(state.series.chapters, item.id);
    nav.seriesLoaded = true;
    if (previous) nav.previous = { to: readerPath(previous.id, seriesId), title: previous.title };
    if (next) nav.next = { to: readerPath(next.id, seriesId), title: next.title };
  }
  return nav;
}
