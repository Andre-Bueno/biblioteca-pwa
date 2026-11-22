import type { ReadingDirection } from '../../../shared/preferences';
import type { Step } from '../shell/types';

export type TapZone = Step | 'center';
export type KeyAction = Step | 'first' | 'last';

/** Share of the width that counts as the left/right tap zone. */
export const EDGE_ZONE = 0.3;
export const SWIPE_MIN_PX = 50;
export const TAP_MAX_MOVE_PX = 10;

/**
 * Left/right zones turn the page according to the reading direction: in rtl the LEFT side goes
 * forward (the next page is to the left), in ltr the RIGHT side does. Vertical mode and zoomed
 * pages have no page-turn zones: every tap is a "center" tap.
 */
export function tapZone(
  x: number,
  width: number,
  mode: ReadingDirection,
  zoomed: boolean,
): TapZone {
  if (mode === 'vertical' || zoomed || width <= 0) return 'center';
  const ratio = x / width;
  const side = ratio < EDGE_ZONE ? 'left' : ratio > 1 - EDGE_ZONE ? 'right' : null;
  if (side === null) return 'center';
  const leftIsNext = mode === 'rtl';
  return (side === 'left') === leftIsNext ? 'next' : 'prev';
}

/** Horizontal swipe. In rtl, swiping to the right brings the next page; in ltr, to the left. */
export function swipeStep(dx: number, dy: number, mode: ReadingDirection): Step | null {
  if (mode === 'vertical') return null;
  if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) < Math.abs(dy) * 1.5) return null;
  const towardsRight = dx > 0;
  return towardsRight === (mode === 'rtl') ? 'next' : 'prev';
}

export function keyAction(key: string, mode: ReadingDirection): KeyAction | null {
  if (key === 'Home') return 'first';
  if (key === 'End') return 'last';
  if (mode === 'vertical') return null; // arrows keep scrolling natively
  if (key === 'ArrowDown' || key === 'PageDown') return 'next';
  if (key === 'ArrowUp' || key === 'PageUp') return 'prev';
  if (key === 'ArrowLeft') return mode === 'rtl' ? 'next' : 'prev';
  if (key === 'ArrowRight') return mode === 'rtl' ? 'prev' : 'next';
  return null;
}
