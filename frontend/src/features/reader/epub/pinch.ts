/** Time after a multi-touch gesture ends during which scroll/resize noise is not a user move. */
export const PINCH_SETTLE_MS = 600;
/** A multi-touch with no touch event for this long is considered lost (missing touchend). */
export const PINCH_STALE_MS = 2000;
/** How long after a width change the reader keeps its position while the layout reflows. */
export const RESIZE_HOLD_MS = 1000;
/** The hold is extended by this much each time a chapter height changes during it. */
export const RESIZE_EXTEND_MS = 400;
/** A resize right after the user's own scroll is not held (it must not fight the user). */
export const USER_SCROLL_MS = 150;

/**
 * Tracks multi-touch (pinch zoom). While two or more fingers are down, and for a short time after
 * the last one lifts, the reader must not read the gesture as a swipe, a centre tap or a scroll
 * to save: zoom is a view change, never a position change.
 */
export interface PinchGuard {
  /** Feed `event.touches.length` from touchmove / touchend. */
  touches: (count: number, now: number) => void;
  /** touchstart: a single finger means any earlier pinch is over (its touchend was lost). */
  start: (count: number, now: number) => void;
  /** touchcancel, window blur, page hidden: forget any pinch in progress. */
  reset: () => void;
  /** True while a pinch is in progress or has just ended. */
  blocked: (now: number) => boolean;
  /** Milliseconds until `blocked` turns false (0 when it is not blocked). */
  remaining: (now: number) => number;
}

export function createPinchGuard(): PinchGuard {
  let multi = false;
  let until = 0;
  let last = 0;
  const expire = (now: number) => {
    if (multi && now - last > PINCH_STALE_MS) {
      multi = false;
      until = 0;
    }
  };
  return {
    touches(count, now) {
      expire(now);
      last = now;
      if (count > 1) {
        multi = true;
        until = now + PINCH_SETTLE_MS;
      } else if (count === 0 && multi) {
        multi = false;
        until = now + PINCH_SETTLE_MS;
      }
    },
    start(count, now) {
      expire(now);
      last = now;
      if (count > 1) {
        multi = true;
        until = now + PINCH_SETTLE_MS;
      } else if (count === 1) {
        multi = false;
        until = 0;
      }
    },
    reset() {
      multi = false;
      until = 0;
    },
    blocked(now) {
      expire(now);
      return multi || now < until;
    },
    remaining(now) {
      expire(now);
      return multi ? PINCH_STALE_MS : Math.max(0, until - now);
    },
  };
}

/**
 * Keeps the reading position across a layout reflow caused by a viewport WIDTH change (browser
 * zoom, rotation). Height-only changes (Safari toolbars) never hold, and neither does a resize
 * that comes right after the user's own scroll; a user scroll during the hold ends it.
 */
export interface ReflowHold {
  /** A resize happened. Returns true when the position must be held and re-applied. */
  onResize: (width: number, now: number) => boolean;
  /** The user scrolled on purpose. */
  userMoved: (now: number) => void;
  active: (now: number) => boolean;
  extend: (now: number) => void;
  remaining: (now: number) => number;
}

export function createReflowHold(initialWidth: number): ReflowHold {
  let width = initialWidth;
  let until = 0;
  let lastUser = Number.NEGATIVE_INFINITY;
  return {
    onResize(next, now) {
      if (next === width) return false; // only the height changed
      width = next;
      if (now - lastUser < USER_SCROLL_MS) return false;
      until = now + RESIZE_HOLD_MS;
      return true;
    },
    userMoved(now) {
      lastUser = now;
      until = 0;
    },
    active: (now) => now < until,
    extend(now) {
      if (now < until) until = Math.max(until, now + RESIZE_EXTEND_MS);
    },
    remaining: (now) => Math.max(0, until - now),
  };
}
