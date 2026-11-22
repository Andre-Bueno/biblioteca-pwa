import { useCallback, useEffect, useRef } from 'react';

interface Params {
  pageCount: number;
  /** Page the reader opened on (the saved one): progress must not go below it by itself. */
  initialPage: number;
  jump: { page: number; nonce: number };
  onVisiblePage: (page: number) => void;
}

/** Pages mounted around the current one; the others keep only their (measured) height. */
export const STRIP_WINDOW = 3;

const SUPPRESS_MS = 400;
const GESTURE_EVENTS = ['wheel', 'touchmove'] as const;
const SCROLL_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);

/**
 * Webtoon strip behaviour: scrolls to the requested page and reports which page crosses the
 * middle of the screen.
 *
 * While images load, the layout shifts and the observer would report earlier pages, which would
 * REGRESS the saved progress. So reports are accepted only when
 *  - the target page has loaded and been positioned (we scroll to it again after it loads), or
 *  - the user has scrolled (wheel / touch / scroll keys);
 * and without a user gesture a page lower than the initial one is never reported.
 */
export function useVerticalStrip({ pageCount, initialPage, jump, onVisiblePage }: Params) {
  const ref = useRef<HTMLDivElement>(null);
  const heights = useRef(new Map<number, number>());
  const suppressUntil = useRef(0);
  const positioning = useRef<number | null>(null); // page we are still waiting to see loaded
  const positioned = useRef(false);
  const gesture = useRef(false);
  const scrolledSinceJump = useRef(false);

  const scrollTo = useCallback((page: number) => {
    const target = ref.current?.querySelector<HTMLElement>(`[data-page="${page}"]`);
    suppressUntil.current = Date.now() + SUPPRESS_MS;
    target?.scrollIntoView?.({ block: 'start' }); // not implemented in some test environments
  }, []);

  useEffect(() => {
    positioning.current = jump.page;
    scrolledSinceJump.current = false;
    scrollTo(jump.page);
  }, [jump, scrollTo]);

  const heightOf = useCallback((page: number) => heights.current.get(page), []);

  // A page image finished loading: remember its height; if it is the target of the last jump,
  // put it back at the top (the layout moved while the images above it were loading).
  const onPageLoaded = useCallback(
    (page: number, height: number) => {
      if (height > 0) heights.current.set(page, height);
      if (page !== positioning.current) return;
      positioning.current = null;
      if (!scrolledSinceJump.current) scrollTo(page);
      positioned.current = true;
    },
    [scrollTo],
  );

  useEffect(() => {
    const mark = () => {
      gesture.current = true;
      scrolledSinceJump.current = true;
    };
    const onKey = (event: KeyboardEvent) => {
      if (SCROLL_KEYS.has(event.key)) mark();
    };
    for (const name of GESTURE_EVENTS) window.addEventListener(name, mark, { passive: true });
    window.addEventListener('keydown', onKey);
    return () => {
      for (const name of GESTURE_EVENTS) window.removeEventListener(name, mark);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  useEffect(() => {
    const container = ref.current;
    if (!container || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (Date.now() < suppressUntil.current) return;
        if (!gesture.current && !positioned.current) return; // still settling after the resume
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const value = Number((entry.target as HTMLElement).dataset.page);
          if (!Number.isFinite(value)) continue;
          if (!gesture.current && value < initialPage) continue; // layout shift, not the user
          onVisiblePage(value);
        }
      },
      // A thin band across the middle of the screen: the page under it is "the current one".
      { rootMargin: '-49% 0px -49% 0px' },
    );
    container.querySelectorAll('[data-page]').forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [pageCount, initialPage, onVisiblePage]);

  return { ref, heightOf, onPageLoaded };
}
