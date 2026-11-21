import { useCallback, useEffect, useRef, type RefObject } from 'react';
import {
  bpFromScroll,
  isCenterTap,
  parseGotoHref,
  scrollTopFromBp,
  swipeChapterStep,
} from '../locator';
import { createPinchGuard, createReflowHold } from '../pinch';

export interface FrameCallbacks {
  /**
   * Scroll position of the chapter. `report` is false while the position is only "settling"
   * after a load (or lower than where the chapter opened) and no user gesture happened: such a
   * value must never be saved, or the saved progress would regress by itself.
   */
  onPosition: (chapter: number, bp: number, report: boolean) => void;
  onGoto: (index: number, anchor: string | null) => void;
  onToggleControls: () => void;
  onKey: (event: KeyboardEvent) => void;
  onSwipe: (step: 'chapter-prev' | 'chapter-next') => void;
  onLoaded: (ok: boolean) => void;
}

interface Params {
  /** The iframe element (created by the component that renders it). */
  frameRef: RefObject<HTMLIFrameElement | null>;
  /** Chapter currently requested; the loaded document belongs to it. */
  chapter: number;
  /** Position (basis points) a loaded document resumes at; kept current by this hook. */
  positionRef: RefObject<number>;
  /** Anchor to scroll to on the next load (set by internal links / TOC), consumed on load. */
  anchorRef: RefObject<string | null>;
  callbacks: FrameCallbacks;
}

interface Session {
  gesture: boolean;
  settled: boolean;
}

const IMAGE_WAIT_MS = 3000;
const SCROLL_KEYS = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);

function scrollerOf(doc: Document): HTMLElement {
  return (doc.scrollingElement as HTMLElement | null) ?? doc.documentElement;
}

/**
 * Everything that touches the (same-origin, sandboxed, script-less) chapter iframe: restores the
 * position once the images are in (re-applying it as they load, because the layout shifts),
 * watches the scroll, and turns clicks / taps / keys / swipes into reader actions.
 * The book HTML itself is never read into the app: only geometry and `a[href]` values.
 */
export function useEpubFrame({ frameRef, chapter, positionRef, anchorRef, callbacks }: Params) {
  const latest = useRef(callbacks);
  const chapterRef = useRef(chapter);
  const session = useRef<Session>({ gesture: false, settled: false });
  const cleanup = useRef<(() => void) | null>(null);

  useEffect(() => {
    latest.current = callbacks;
    chapterRef.current = chapter;
  });
  useEffect(() => () => cleanup.current?.(), []);

  const onLoad = useCallback(() => {
    cleanup.current?.();
    cleanup.current = null;
    const frame = frameRef.current;
    const doc = frame?.contentDocument;
    const win = frame?.contentWindow;
    if (!frame || !doc || !win || doc.contentType !== 'text/html' || !doc.body) {
      latest.current.onLoaded(false); // JSON error body, blocked or empty document
      return;
    }

    const loadedChapter = chapterRef.current; // late events of this document keep its chapter
    const state: Session = { gesture: false, settled: false };
    session.current = state;
    const target = positionRef.current ?? 0;
    const anchor = anchorRef.current;
    anchorRef.current = null;
    const floor = anchor ? 0 : target;
    // Listeners are removed one by one (no AbortSignal: the document is from another realm).
    const disposers: (() => void)[] = [];
    const listen = (
      node: EventTarget,
      name: string,
      handler: (event: never) => void,
      passive = false,
    ) => {
      node.addEventListener(name, handler as EventListener, { passive });
      disposers.push(() => node.removeEventListener(name, handler as EventListener));
    };
    const apply = () => {
      const el = scrollerOf(doc);
      const anchored = anchor ? doc.getElementById(anchor) : null;
      if (anchored) el.scrollTop += anchored.getBoundingClientRect().top;
      else el.scrollTop = scrollTopFromBp(target, el.scrollHeight, el.clientHeight);
    };
    const currentBp = () => {
      const el = scrollerOf(doc);
      return bpFromScroll(el.scrollTop, el.scrollHeight, el.clientHeight);
    };

    // Resume: scroll now, and again as each image arrives (the layout above moves).
    apply();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const settle = () => {
      if (state.settled) return;
      state.settled = true;
      if (timer !== null) clearTimeout(timer);
      if (!state.gesture) apply();
      const bp = currentBp();
      positionRef.current = bp;
      latest.current.onPosition(loadedChapter, bp, state.gesture || bp >= floor);
    };
    const waiting = Array.from(doc.images).filter((image) => !image.complete);
    if (waiting.length === 0) {
      settle();
    } else {
      let left = waiting.length;
      const done = () => {
        if (!state.gesture) apply();
        left -= 1;
        if (left <= 0) settle();
      };
      for (const image of waiting) {
        listen(image, 'load', done);
        listen(image, 'error', done);
      }
      timer = setTimeout(settle, IMAGE_WAIT_MS);
    }
    latest.current.onLoaded(true);

    const pinch = createPinchGuard();
    const hold = createReflowHold(win.innerWidth);
    // Zoom (pinch, ctrl + wheel / +) reflows the page: keep the position the reader was at and
    // never save what the browser scrolled meanwhile (but look again once the noise is over).
    const applyBp = (value: number) => {
      const el = scrollerOf(doc);
      const top = scrollTopFromBp(value, el.scrollHeight, el.clientHeight);
      if (Math.abs(el.scrollTop - top) >= 1) el.scrollTop = top;
    };
    listen(win, 'resize', () => {
      // Width changes only: a height-only resize (Safari toolbars) neither holds nor re-applies.
      if (hold.onResize(win.innerWidth, Date.now()) && state.settled) {
        applyBp(positionRef.current ?? 0);
      }
    });
    let recheck: ReturnType<typeof setTimeout> | null = null;
    const evaluate = () => {
      if (!state.settled && !state.gesture) return; // still settling
      const now = Date.now();
      const wait = Math.max(pinch.remaining(now), hold.remaining(now));
      if (wait > 0) {
        recheck ??= setTimeout(() => {
          recheck = null;
          evaluate();
        }, wait + 30);
        return;
      }
      const bp = currentBp();
      positionRef.current = bp;
      latest.current.onPosition(loadedChapter, bp, state.gesture || bp >= floor);
    };
    listen(win, 'scroll', evaluate);
    disposers.push(() => {
      if (recheck !== null) clearTimeout(recheck);
    });
    const reset = () => pinch.reset();
    listen(win, 'blur', reset);
    listen(doc, 'visibilitychange', reset);

    const markGesture = () => {
      state.gesture = true;
      hold.userMoved(Date.now()); // a user scroll ends any reflow hold
    };
    listen(
      doc,
      'wheel',
      (event: WheelEvent) => {
        if (!event.ctrlKey) markGesture(); // ctrl + wheel is the browser zoom
      },
      true,
    );
    listen(
      doc,
      'touchmove',
      (event: TouchEvent) => {
        const now = Date.now();
        pinch.touches(event.touches.length, now);
        if (!pinch.blocked(now)) markGesture();
      },
      true,
    );
    listen(doc, 'touchcancel', reset, true);

    let touchStart: { x: number; y: number } | null = null;
    listen(doc, 'touchstart', (event: TouchEvent) => {
      pinch.start(event.touches.length, Date.now());
      const touch = event.touches[0];
      touchStart =
        touch && event.touches.length === 1 ? { x: touch.clientX, y: touch.clientY } : null;
    });
    listen(doc, 'touchend', (event: TouchEvent) => {
      pinch.touches(event.touches.length, Date.now());
      const touch = event.changedTouches[0];
      const start = touchStart;
      touchStart = null;
      if (!touch || !start) return;
      if (pinch.blocked(Date.now())) return; // a pinch is never a page swipe
      if (win.getSelection()?.toString()) return;
      const step = swipeChapterStep(touch.clientX - start.x, touch.clientY - start.y);
      if (step) latest.current.onSwipe(step);
    });

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
        } else if (href?.startsWith('#')) {
          markGesture(); // in-chapter anchor: native jump, counts as a user move
        } else {
          event.preventDefault(); // the iframe must never navigate away on its own
        }
        return;
      }
      if (win.getSelection()?.toString()) return; // selecting text is not a tap
      if (pinch.blocked(Date.now())) return; // end of a pinch is not a tap
      if (isCenterTap(event.clientX, win.innerWidth)) latest.current.onToggleControls();
    });

    cleanup.current = () => {
      for (const dispose of disposers) dispose();
      if (timer !== null) clearTimeout(timer);
    };
  }, [frameRef, positionRef, anchorRef]);

  /** Scrolls the chapter by a fraction of the visible height (user action). */
  const scrollBy = useCallback(
    (fraction: number) => {
      const doc = frameRef.current?.contentDocument;
      if (!doc) return;
      session.current.gesture = true;
      const el = scrollerOf(doc);
      el.scrollTop += fraction * el.clientHeight;
    },
    [frameRef],
  );

  const scrollToEdge = useCallback(
    (edge: 'top' | 'bottom') => {
      const doc = frameRef.current?.contentDocument;
      if (!doc) return;
      session.current.gesture = true;
      const el = scrollerOf(doc);
      el.scrollTop = edge === 'top' ? 0 : el.scrollHeight;
    },
    [frameRef],
  );

  return { onLoad, scrollBy, scrollToEdge };
}
