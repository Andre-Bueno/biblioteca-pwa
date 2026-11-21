import { CHAPTER_STRIDE, clampBp, clampChapter } from './locator';

/** Chapters mounted (as iframes) behind and ahead of the current one; the rest are placeholders. */
export const STRIP_BEHIND = 1;
export const STRIP_AHEAD = 3;

/** Settling time after a programmatic scroll during which scroll events are not user moves. */
export const STRIP_SUPPRESS_MS = 400;

export interface StripBlock {
  top: number;
  height: number;
}

/** Inclusive range of chapter indexes that keep a live iframe around `current`. */
export function stripWindow(current: number, count: number): { from: number; to: number } {
  if (count <= 0) return { from: 0, to: -1 };
  const at = clampChapter(current, count);
  return { from: Math.max(0, at - STRIP_BEHIND), to: Math.min(count - 1, at + STRIP_AHEAD) };
}

/** Chapter under the top edge of the viewport and the offset (basis points) inside it. */
export function locateInStrip(
  scrollTop: number,
  blocks: readonly StripBlock[],
): { chapter: number; bp: number } {
  if (blocks.length === 0 || !Number.isFinite(scrollTop)) return { chapter: 0, bp: 0 };
  let chapter = 0;
  for (const [index, entry] of blocks.entries()) {
    if (entry.top <= scrollTop + 0.5) chapter = index;
    else break;
  }
  const block = blocks.at(chapter);
  if (!block || !(block.height > 0)) return { chapter, bp: 0 };
  return { chapter, bp: clampBp(((scrollTop - block.top) / block.height) * CHAPTER_STRIDE) };
}

/** Inverse of `locateInStrip`: where to scroll to show `bp` of this chapter at the top. */
export function scrollTopForPosition(block: StripBlock, bp: number): number {
  return block.top + (clampBp(bp) / CHAPTER_STRIDE) * Math.max(0, block.height);
}

/**
 * Lets the chapter document be as tall as its content. Books (manga/fixed layout) often ship
 * `html, body { height: 100% }` (or `min-height`), which makes the `html` box exactly as tall as
 * the iframe: the measure then only ever echoes the frame height, the chapter stays one screen
 * tall and the page ends up clipped / scrolling inside its frame instead of flowing in the strip.
 * Set through CSSOM (no script runs in the book, no stylesheet injected), so the sandbox and
 * the chapter CSP are untouched. Percent heights of descendants resolve to `auto` afterwards.
 */
export function unlockDocumentHeight(doc: Document): void {
  for (const element of [doc.documentElement, doc.body]) {
    if (!element?.style) continue;
    element.style.setProperty('height', 'auto', 'important');
    element.style.setProperty('min-height', '0', 'important');
  }
}

/**
 * Content height of a chapter document. The `html` box is as tall as its content (not as the
 * iframe), so the frame can also shrink; `scrollHeight` is only a fallback.
 */
export function measureFrameHeight(doc: Document): number {
  const root = doc.documentElement;
  const value = root.offsetHeight || root.scrollHeight || doc.body?.offsetHeight || 0;
  return Number.isFinite(value) ? Math.ceil(value) : 0;
}
