import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { BP_MAX, encodeLocator, isCenterTap, parseGotoHref } from '../locator';
import {
  STRIP_SUPPRESS_MS,
  locateInStrip,
  measureFrameHeight,
  scrollTopForPosition,
  stripWindow,
  type StripBlock,
} from '../strip';

export interface StripJump {
  chapter: number;
  bp: number;
  nonce: number;
}

export interface StripCallbacks {
  /** Chapter and offset under the top of the screen. `report` false = never save this value. */
  onPosition: (chapter: number, bp: number, report: boolean) => void;
  onGoto: (index: number, anchor: string | null) => void;
  onToggleControls: () => void;
  onKey: (event: KeyboardEvent) => void;
}

interface Params {
  enabled: boolean;
  /** Chapter at the top of the screen (decides which chapters keep an iframe). */
  chapter: number;
  count: number;
  /** Where the strip opened: progress is never lowered below it without a user gesture. */
  initial: { chapter: number; bp: number };
  jump: StripJump;
  callbacks: StripCallbacks;
}

const SCROLL_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);

function fallbackHeight(): number {
  return typeof window === 'undefined' ? 800 : Math.max(200, window.innerHeight);
}

/**
 * Continuous vertical reading of a book (webtoon style): every chapter is its own iframe, sized
 * to its content, stacked in one scroll container. Only a window of chapters around the current
 * one is mounted; the others keep their last measured height so the scroll does not jump.
 *
 * Progress follows the manga strip rules: while the layout settles after the resume (images
 * load, heights change) nothing is reported, and without a user gesture nothing below the
 * opening position is ever reported, so the saved progress cannot regress by itself.
 */
export function useEpubStrip({ enabled, chapter, count, initial, jump, callbacks }: Params) {
  const containerRef = useRef<HTMLDivElement>(null);
  const heightsRef = useRef(new Map<number, number>());
  const [heights, setHeights] = useState<ReadonlyMap<number, number>>(() => new Map());
  const latest = useRef(callbacks);
  const topChapter = useRef(chapter);
  const state = useRef({
    gesture: false,
    positioned: false,
    scrolledSinceJump: false,
    suppressUntil: 0,
    floor: encodeLocator(initial.chapter, initial.bp),
    target: jump.chapter,
    targetBp: jump.bp,
    shift: 0,
    rescroll: false,
  });
  const disposers = useRef(new Map<number, () => void>());

  useEffect(() => {
    latest.current = callbacks;
    topChapter.current = chapter;
  });

  const blocks = useCallback((): StripBlock[] => {
    const el = containerRef.current;
    if (!el) return [];
    return Array.from(el.children).map((child) => ({
      top: (child as HTMLElement).offsetTop,
      height: (child as HTMLElement).offsetHeight,
    }));
  }, []);

  const scrollToTarget = useCallback(() => {
    const el = containerRef.current;
    const s = state.current;
    const block = blocks()[s.target];
    if (!el || !block) return;
    s.suppressUntil = Date.now() + STRIP_SUPPRESS_MS;
    el.scrollTop = scrollTopForPosition(block, s.targetBp);
  }, [blocks]);

  // Applies what a height change asks for: keep the view still (chapters above grew or shrank)
  // or put the jump target back at the top (the layout above it moved while it loaded).
  const flush = useCallback(() => {
    const el = containerRef.current;
    const s = state.current;
    if (!el) return;
    if (s.rescroll) {
      s.rescroll = false;
      s.shift = 0;
      if (!s.scrolledSinceJump) {
        scrollToTarget();
        return;
      }
    }
    if (s.shift !== 0) {
      s.suppressUntil = Date.now() + STRIP_SUPPRESS_MS;
      el.scrollTop += s.shift;
      s.shift = 0;
    }
  }, [scrollToTarget]);

  useLayoutEffect(() => {
    flush();
  });

  useEffect(() => {
    if (!enabled) return;
    const s = state.current;
    s.positioned = false;
    s.scrolledSinceJump = false;
    s.gesture = false; // a new jump settles again: only a fresh gesture re-enables reports
    s.target = jump.chapter;
    s.targetBp = jump.bp;
    if (jump.nonce > 0) s.floor = 0; // the user moved on purpose
    scrollToTarget();
  }, [enabled, jump, scrollToTarget]);

  const markGesture = useCallback(() => {
    state.current.gesture = true;
    state.current.scrolledSinceJump = true;
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!enabled || !el) return undefined;
    const onScroll = () => {
      const s = state.current;
      if (Date.now() < s.suppressUntil) return;
      if (!s.gesture && !s.positioned) return; // still settling after the resume
      const at = locateInStrip(el.scrollTop, blocks());
      // Bottom of the strip on the last chapter = end of the book (the top-edge offset never gets there).
      if (at.chapter === count - 1 && el.scrollTop + el.clientHeight >= el.scrollHeight - 2) {
        at.bp = BP_MAX;
      }
      topChapter.current = at.chapter;
      const report = s.gesture || encodeLocator(at.chapter, at.bp) >= s.floor;
      latest.current.onPosition(at.chapter, at.bp, report);
    };
    const onKey = (event: KeyboardEvent) => {
      if (SCROLL_KEYS.has(event.key)) markGesture();
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    el.addEventListener('wheel', markGesture, { passive: true });
    el.addEventListener('touchmove', markGesture, { passive: true });
    window.addEventListener('keydown', onKey);
    return () => {
      el.removeEventListener('scroll', onScroll);
      el.removeEventListener('wheel', markGesture);
      el.removeEventListener('touchmove', markGesture);
      window.removeEventListener('keydown', onKey);
    };
  }, [enabled, blocks, markGesture, count]);

  /** A chapter document reported its content height. */
  const onFrameHeight = useCallback(
    (index: number, height: number) => {
      if (!(height > 0)) return;
      const s = state.current;
      const known = heightsRef.current.get(index);
      const previous = known ?? fallbackHeight();
      if (index === s.target && !s.positioned) {
        s.positioned = true;
        s.rescroll = true;
      } else if (index < topChapter.current && height !== previous) {
        s.shift += height - previous; // above the view: keep what the reader is looking at
      }
      if (known === height) {
        flush();
        return;
      }
      heightsRef.current.set(index, height);
      setHeights(new Map(heightsRef.current));
    },
    [flush],
  );

  /**
   * Wires a loaded chapter document: measures it (again as images arrive) and turns clicks,
   * keys and touches into reader actions. Returns the disposer. Only geometry and `a[href]`
   * values are read from the book document.
   */
  const attachFrame = useCallback(
    (index: number, frame: HTMLIFrameElement): { ok: boolean; dispose: () => void } => {
      disposers.current.get(index)?.();
      disposers.current.delete(index);
      const doc = frame.contentDocument;
      const win = frame.contentWindow;
      if (!doc || !win || doc.contentType !== 'text/html' || !doc.body) {
        return { ok: false, dispose: () => undefined };
      }
      const cleanups: (() => void)[] = [];
      const listen = (
        node: EventTarget,
        name: string,
        handler: (event: never) => void,
        passive = false,
      ) => {
        node.addEventListener(name, handler as EventListener, { passive });
        cleanups.push(() => node.removeEventListener(name, handler as EventListener));
      };
      const measure = () => onFrameHeight(index, measureFrameHeight(doc));

      measure();
      for (const image of Array.from(doc.images)) {
        if (image.complete) continue;
        listen(image, 'load', measure);
        listen(image, 'error', measure);
      }
      const Observer = (win as unknown as { ResizeObserver?: typeof ResizeObserver })
        .ResizeObserver;
      if (typeof Observer === 'function') {
        const observer = new Observer(measure);
        observer.observe(doc.documentElement);
        cleanups.push(() => observer.disconnect());
      }

      listen(doc, 'wheel', markGesture, true);
      listen(doc, 'touchmove', markGesture, true);
      listen(doc, 'keydown', (event: KeyboardEvent) => {
        if (SCROLL_KEYS.has(event.key)) markGesture();
        latest.current.onKey(event);
      });
      listen(doc, 'click', (event: MouseEvent) => {
        // The document belongs to another realm, so `instanceof Element` would not work here.
        const element = event.target as Element | null;
        const link = typeof element?.closest === 'function' ? element.closest('a') : null;
        if (link) {
          const href = link.getAttribute('href');
          const goto = parseGotoHref(href);
          if (goto) {
            event.preventDefault();
            latest.current.onGoto(goto.index, goto.anchor);
          } else if (!href?.startsWith('#')) {
            event.preventDefault(); // the iframe must never navigate away on its own
          }
          return;
        }
        if (win.getSelection()?.toString()) return;
        if (isCenterTap(event.clientX, win.innerWidth)) latest.current.onToggleControls();
      });

      const dispose = () => {
        for (const run of cleanups) run();
        disposers.current.delete(index);
      };
      disposers.current.set(index, dispose);
      return { ok: true, dispose };
    },
    [onFrameHeight, markGesture],
  );

  useEffect(
    () => () => {
      for (const dispose of Array.from(disposers.current.values())) dispose();
    },
    [],
  );

  const scrollBy = useCallback(
    (fraction: number) => {
      const el = containerRef.current;
      if (!el) return;
      markGesture();
      el.scrollTop += fraction * el.clientHeight;
    },
    [markGesture],
  );

  const scrollToEdge = useCallback(
    (edge: 'top' | 'bottom') => {
      const el = containerRef.current;
      if (!el) return;
      markGesture();
      el.scrollTop = edge === 'top' ? 0 : el.scrollHeight;
    },
    [markGesture],
  );

  const heightOf = useCallback(
    (index: number) => heights.get(index) ?? fallbackHeight(),
    [heights],
  );

  return {
    containerRef,
    mounted: stripWindow(chapter, count),
    heightOf,
    attachFrame,
    scrollBy,
    scrollToEdge,
  };
}

export type EpubStrip = ReturnType<typeof useEpubStrip>;
