import type { ReadingDirection } from '../../../shared/preferences';
import type { ReaderSource, SourceKind } from '../sources';

/**
 * What the reader is asked to do, independent of where it came from (key, swipe or tap) and of
 * the format. Each viewport decides how to carry an intent out (turn a page, open a chapter,
 * scroll). Pure module: no React, no DOM.
 */
export type ReaderIntent =
  | { type: 'prev' }
  | { type: 'next' }
  | { type: 'first' }
  | { type: 'last' }
  /** Scroll by a share of the visible height (PageUp / PageDown). `sign` -1 is up. */
  | { type: 'scrollPage'; sign: 1 | -1 }
  /** Scroll by a small share of the visible height (arrows up / down). */
  | { type: 'scrollLine'; sign: 1 | -1 }
  /** Top (-1) or bottom (1) of the current scrolling unit (Home / End of a chapter). */
  | { type: 'scrollEdge'; sign: 1 | -1 }
  | { type: 'toggleChrome' };

export const SCROLL_PAGE_FRACTION = 0.9;
export const SCROLL_LINE_FRACTION = 0.1;

/** Share of the visible height an intent of scrolling moves (signed), 0 for other intents. */
export function scrollFraction(intent: ReaderIntent): number {
  if (intent.type === 'scrollPage') return intent.sign * SCROLL_PAGE_FRACTION;
  if (intent.type === 'scrollLine') return intent.sign * SCROLL_LINE_FRACTION;
  return 0;
}

/** Gesture thresholds of one kind of viewport. Defined once here, never copied elsewhere. */
export interface ViewportInput {
  /** Minimum horizontal travel of a swipe. */
  swipeMinPx: number;
  /** How many times larger than the vertical travel a swipe must be (so a scroll is not a swipe). */
  swipeRatio: number;
  /** Share of the width, on each side, that is the left/right zone; the middle is the centre. */
  edgeZone: number;
  /** A pointer that moved more than this is a drag, not a tap. */
  tapMaxMovePx: number;
}

/** Image pages (the finger can only turn the page) and HTML documents (the finger also scrolls). */
export const VIEWPORT_INPUT: Record<SourceKind, ViewportInput> = {
  pages: { swipeMinPx: 50, swipeRatio: 1.5, edgeZone: 0.3, tapMaxMovePx: 10 },
  chapters: { swipeMinPx: 80, swipeRatio: 2, edgeZone: 0.25, tapMaxMovePx: 10 },
};

export interface InputContext {
  /** Reading mode of the user (`rtl`, `ltr` or continuous `vertical`). */
  mode: ReadingDirection;
  source: Pick<ReaderSource, 'kind' | 'capabilities'>;
  /** The page is zoomed in: swipes and edge taps are the browser's, not the reader's. */
  zoomed: boolean;
}

export function createInputContext(
  source: Pick<ReaderSource, 'kind' | 'capabilities'>,
  mode: ReadingDirection,
  zoomed = false,
): InputContext {
  return { mode, source, zoomed };
}

export function viewportInput(context: InputContext): ViewportInput {
  return VIEWPORT_INPUT[context.source.kind];
}

/** The direction that actually applies: `rtl` and `ltr` only if the source honors them. */
export function effectiveMode(context: InputContext): ReadingDirection {
  if (context.mode === 'vertical') return 'vertical';
  return context.source.capabilities.honorsDirection ? context.mode : 'ltr';
}

const TOGGLE: ReaderIntent = { type: 'toggleChrome' };

/** rtl: the next unit is on the LEFT; ltr and vertical: on the right. */
function horizontal(context: InputContext, towardsLeft: boolean): ReaderIntent {
  const leftIsNext = effectiveMode(context) === 'rtl';
  return { type: towardsLeft === leftIsNext ? 'next' : 'prev' };
}

export function keyIntent(key: string, context: InputContext): ReaderIntent | null {
  const pages = context.source.kind === 'pages';
  switch (key) {
    case 'Home':
      return pages ? { type: 'first' } : { type: 'scrollEdge', sign: -1 };
    case 'End':
      return pages ? { type: 'last' } : { type: 'scrollEdge', sign: 1 };
    case 'ArrowLeft':
      return horizontal(context, true);
    case 'ArrowRight':
      return horizontal(context, false);
    case 'ArrowUp':
    case 'ArrowDown': {
      const sign = key === 'ArrowDown' ? 1 : -1;
      if (!pages) return { type: 'scrollLine', sign };
      // Pages turn; in the continuous strip the arrows keep scrolling natively.
      return context.mode === 'vertical' ? null : { type: sign === 1 ? 'next' : 'prev' };
    }
    case 'PageUp':
    case 'PageDown': {
      const sign = key === 'PageDown' ? 1 : -1;
      if (!pages) return { type: 'scrollPage', sign };
      return context.mode === 'vertical' ? null : { type: sign === 1 ? 'next' : 'prev' };
    }
    default:
      return null;
  }
}

/** Horizontal swipe. In rtl, swiping to the right brings the next unit; in ltr, to the left. */
export function swipeIntent(dx: number, dy: number, context: InputContext): ReaderIntent | null {
  const mode = effectiveMode(context);
  if (mode === 'vertical' || context.zoomed) return null;
  const { swipeMinPx, swipeRatio } = viewportInput(context);
  if (Math.abs(dx) < swipeMinPx || Math.abs(dx) < Math.abs(dy) * swipeRatio) return null;
  const towardsRight = dx > 0;
  return { type: towardsRight === (mode === 'rtl') ? 'next' : 'prev' };
}

/**
 * Tap at `x` (0 to `width`). The middle toggles the controls. The sides turn the unit only where
 * the source says so (`edgeTapsStep`: pages); on chapters they do nothing. Continuous mode and a
 * zoomed page have no sides: every tap is a centre tap.
 */
export function tapIntent(x: number, width: number, context: InputContext): ReaderIntent | null {
  if (width <= 0) return TOGGLE;
  const { edgeZone } = viewportInput(context);
  const ratio = x / width;
  const side = ratio < edgeZone ? 'left' : ratio > 1 - edgeZone ? 'right' : null;
  if (side === null) return TOGGLE;
  if (!context.source.capabilities.edgeTapsStep) return null;
  if (effectiveMode(context) === 'vertical' || context.zoomed) return TOGGLE;
  return horizontal(context, side === 'left');
}
