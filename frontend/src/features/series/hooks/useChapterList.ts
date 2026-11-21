import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Chapter } from '../../../shared/series';

export const WINDOW_SIZE = 50;

export type GoToResult = 'found' | 'notfound' | 'invalid';

/** Parses "12", " 12.5 " or "12,5"; anything else is invalid. */
export function parseChapterNumber(text: string): number | null {
  const normalized = text.trim().replace(',', '.');
  if (normalized.length === 0 || normalized.length > 10 || !/^[0-9.]+$/.test(normalized))
    return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

/**
 * Renders a long chapter list in windows of WINDOW_SIZE rows ("show more"), and can jump to a
 * chapter by number: the window grows to include it, then the row is scrolled into view.
 */
export function useChapterList(chapters: Chapter[]) {
  const [visibleCount, setVisibleCount] = useState(WINDOW_SIZE);
  const [highlightId, setHighlightId] = useState<string | null>(null);

  const visible = useMemo(() => chapters.slice(0, visibleCount), [chapters, visibleCount]);
  const remaining = Math.max(0, chapters.length - visible.length);

  const showMore = useCallback(() => setVisibleCount((count) => count + WINDOW_SIZE), []);

  const goToNumber = useCallback(
    (text: string): GoToResult => {
      const wanted = parseChapterNumber(text);
      if (wanted === null) return 'invalid';
      const index = chapters.findIndex((chapter) => chapter.number === wanted);
      const target = chapters.find((chapter) => chapter.number === wanted);
      if (index < 0 || !target) return 'notfound';
      setVisibleCount((count) =>
        Math.max(count, Math.ceil((index + 1) / WINDOW_SIZE) * WINDOW_SIZE),
      );
      setHighlightId(target.id);
      return 'found';
    },
    [chapters],
  );

  useEffect(() => {
    if (!highlightId) return;
    const row = document.getElementById(`chapter-${highlightId}`);
    // scrollIntoView does not exist in every test DOM; the highlight still works without it.
    row?.scrollIntoView?.({ block: 'center' });
  }, [highlightId]);

  return { visible, remaining, showMore, goToNumber, highlightId };
}
