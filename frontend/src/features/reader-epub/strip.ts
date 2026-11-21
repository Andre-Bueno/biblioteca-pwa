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
 * Content height of a chapter document. The `html` box is as tall as its content (not as the
 * iframe), so the frame can also shrink; `scrollHeight` is only a fallback.
 */
export function measureFrameHeight(doc: Document): number {
  const root = doc.documentElement;
  const value = root.offsetHeight || root.scrollHeight || doc.body?.offsetHeight || 0;
  return Number.isFinite(value) ? Math.ceil(value) : 0;
}
