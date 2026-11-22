import { BOOK_FONT_MAX, BOOK_FONT_MIN } from '../../../shared/preferences';

/** Progress locator of a book: `chapter_index * 10000 + offset_bp` (offset in basis points). */
export const CHAPTER_STRIDE = 10000;
export const BP_MAX = CHAPTER_STRIDE - 1;
export const FONT_STEP = 10;

export function clampBp(bp: number): number {
  if (!Number.isFinite(bp)) return 0;
  return Math.min(BP_MAX, Math.max(0, Math.round(bp)));
}

export function clampChapter(chapter: number, count: number): number {
  if (!Number.isFinite(chapter) || count <= 0) return 0;
  return Math.min(count - 1, Math.max(0, Math.trunc(chapter)));
}

export function encodeLocator(chapter: number, bp: number): number {
  return Math.max(0, Math.trunc(chapter)) * CHAPTER_STRIDE + clampBp(bp);
}

export function decodeLocator(locator: number | null): { chapter: number; bp: number } {
  if (locator === null || !Number.isFinite(locator) || locator < 0) return { chapter: 0, bp: 0 };
  const whole = Math.trunc(locator);
  return { chapter: Math.floor(whole / CHAPTER_STRIDE), bp: whole % CHAPTER_STRIDE };
}

/** Scroll position inside a chapter, in basis points of the scrollable distance. */
export function bpFromScroll(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
): number {
  const range = scrollHeight - clientHeight;
  if (!(range > 0)) return 0;
  return clampBp((scrollTop / range) * BP_MAX);
}

export function scrollTopFromBp(bp: number, scrollHeight: number, clientHeight: number): number {
  const range = Math.max(0, scrollHeight - clientHeight);
  return (clampBp(bp) / BP_MAX) * range;
}

/** Whole-book percent (0 to 100), estimated from the chapter and the position in it. */
export function bookPercent(chapter: number, bp: number, count: number): number {
  if (count <= 0) return 0;
  const value = ((chapter + clampBp(bp) / CHAPTER_STRIDE) / count) * 100;
  return Math.min(100, Math.max(0, Math.round(value)));
}

/** Internal links arrive rewritten by the server as `?goto=<index>#anchor`. */
export function parseGotoHref(
  href: string | null,
): { index: number; anchor: string | null } | null {
  if (!href) return null;
  if (!href.startsWith('?goto=')) return null;
  const rest = href.slice('?goto='.length);
  const hash = rest.indexOf('#');
  const digits = hash < 0 ? rest : rest.slice(0, hash);
  if (!/^\d{1,6}$/.test(digits)) return null;
  const fragment = hash < 0 ? '' : rest.slice(hash + 1);
  return { index: Number(digits), anchor: fragment ? safeDecode(fragment) : null };
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function stepFontScale(current: number, direction: 1 | -1): number {
  const next = current + direction * FONT_STEP;
  return Math.min(BOOK_FONT_MAX, Math.max(BOOK_FONT_MIN, next));
}
