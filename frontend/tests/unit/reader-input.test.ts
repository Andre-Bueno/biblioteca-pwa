import { describe, expect, it } from 'vitest';
import {
  VIEWPORT_INPUT,
  createInputContext,
  effectiveMode,
  keyIntent,
  scrollFraction,
  swipeIntent,
  tapIntent,
  type ReaderIntent,
} from '../../src/features/reader/input';
import {
  createBookChaptersSource,
  createImagePagesSource,
} from '../../src/features/reader/sources';
import type { ReadingDirection } from '../../src/shared/preferences';

const pages = createImagePagesSource(10);
const chapters = createBookChaptersSource({ chapters: [], toc: [] });
const NEXT: ReaderIntent = { type: 'next' };
const PREV: ReaderIntent = { type: 'prev' };
const TOGGLE: ReaderIntent = { type: 'toggleChrome' };

const ctx = (kind: 'pages' | 'chapters', mode: ReadingDirection, zoomed = false) =>
  createInputContext(kind === 'pages' ? pages : chapters, mode, zoomed);

describe('keyIntent: direction x key x source', () => {
  // [kind, mode, key, expected]
  const table: ['pages' | 'chapters', ReadingDirection, string, ReaderIntent | null][] = [
    ['pages', 'rtl', 'ArrowLeft', NEXT],
    ['pages', 'rtl', 'ArrowRight', PREV],
    ['pages', 'ltr', 'ArrowLeft', PREV],
    ['pages', 'ltr', 'ArrowRight', NEXT],
    ['chapters', 'rtl', 'ArrowLeft', NEXT],
    ['chapters', 'rtl', 'ArrowRight', PREV],
    ['chapters', 'ltr', 'ArrowLeft', PREV],
    ['chapters', 'ltr', 'ArrowRight', NEXT],
    // continuous: left / right are previous / next unit, like ltr
    ['pages', 'vertical', 'ArrowLeft', PREV],
    ['pages', 'vertical', 'ArrowRight', NEXT],
    ['chapters', 'vertical', 'ArrowLeft', PREV],
    ['chapters', 'vertical', 'ArrowRight', NEXT],
    // pages turn with up / down and the page keys in paged modes
    ['pages', 'rtl', 'ArrowDown', NEXT],
    ['pages', 'ltr', 'PageDown', NEXT],
    ['pages', 'rtl', 'ArrowUp', PREV],
    ['pages', 'ltr', 'PageUp', PREV],
    // ... and keep scrolling natively in the continuous strip
    ['pages', 'vertical', 'ArrowDown', null],
    ['pages', 'vertical', 'PageUp', null],
    // chapters scroll with up / down and the page keys, in every mode
    ['chapters', 'rtl', 'ArrowDown', { type: 'scrollLine', sign: 1 }],
    ['chapters', 'ltr', 'ArrowUp', { type: 'scrollLine', sign: -1 }],
    ['chapters', 'vertical', 'ArrowDown', { type: 'scrollLine', sign: 1 }],
    ['chapters', 'rtl', 'PageDown', { type: 'scrollPage', sign: 1 }],
    ['chapters', 'vertical', 'PageUp', { type: 'scrollPage', sign: -1 }],
    // Home / End: first / last page; top / bottom of a chapter
    ['pages', 'rtl', 'Home', { type: 'first' }],
    ['pages', 'vertical', 'End', { type: 'last' }],
    ['chapters', 'ltr', 'Home', { type: 'scrollEdge', sign: -1 }],
    ['chapters', 'rtl', 'End', { type: 'scrollEdge', sign: 1 }],
    ['pages', 'rtl', 'a', null],
    ['chapters', 'ltr', 'Enter', null],
  ];
  it.each(table)('%s / %s / %s', (kind, mode, key, expected) => {
    expect(keyIntent(key, ctx(kind, mode))).toEqual(expected);
  });
});

describe('swipeIntent: direction x gesture x source', () => {
  // dx > 0 is a swipe towards the right
  const table: ['pages' | 'chapters', ReadingDirection, number, number, ReaderIntent | null][] = [
    ['pages', 'rtl', 120, 5, NEXT],
    ['pages', 'rtl', -120, 5, PREV],
    ['pages', 'ltr', -120, 5, NEXT],
    ['pages', 'ltr', 120, 5, PREV],
    ['chapters', 'rtl', 120, 5, NEXT],
    ['chapters', 'rtl', -120, 5, PREV],
    ['chapters', 'ltr', -120, 5, NEXT],
    ['chapters', 'ltr', 120, 5, PREV],
    ['pages', 'vertical', 200, 0, null],
    ['chapters', 'vertical', 200, 0, null],
  ];
  it.each(table)('%s / %s / dx=%i dy=%i', (kind, mode, dx, dy, expected) => {
    expect(swipeIntent(dx, dy, ctx(kind, mode))).toEqual(expected);
  });

  it('thresholds are per viewport: pages 50 px and 1.5x, chapters 80 px and 2x', () => {
    expect(VIEWPORT_INPUT.pages).toMatchObject({ swipeMinPx: 50, swipeRatio: 1.5 });
    expect(VIEWPORT_INPUT.chapters).toMatchObject({ swipeMinPx: 80, swipeRatio: 2 });
    expect(swipeIntent(60, 0, ctx('pages', 'ltr'))).toEqual(PREV);
    expect(swipeIntent(60, 0, ctx('chapters', 'ltr'))).toBeNull();
    expect(swipeIntent(80, 50, ctx('pages', 'ltr'))).toEqual(PREV); // 80 >= 75
    expect(swipeIntent(80, 50, ctx('chapters', 'ltr'))).toBeNull(); // 80 < 100
    expect(swipeIntent(30, 0, ctx('pages', 'rtl'))).toBeNull();
    expect(swipeIntent(80, 90, ctx('pages', 'rtl'))).toBeNull();
  });

  it('a zoomed page never swipes', () => {
    expect(swipeIntent(200, 0, ctx('pages', 'rtl', true))).toBeNull();
  });
});

describe('tapIntent: zones, direction and capabilities', () => {
  it('pages: the sides turn by direction, the middle toggles the controls', () => {
    expect(tapIntent(10, 400, ctx('pages', 'rtl'))).toEqual(NEXT);
    expect(tapIntent(390, 400, ctx('pages', 'rtl'))).toEqual(PREV);
    expect(tapIntent(390, 400, ctx('pages', 'ltr'))).toEqual(NEXT);
    expect(tapIntent(10, 400, ctx('pages', 'ltr'))).toEqual(PREV);
    for (const mode of ['rtl', 'ltr'] as const) {
      expect(tapIntent(200, 400, ctx('pages', mode))).toEqual(TOGGLE);
    }
  });

  it('pages: continuous mode and a zoomed page have no sides', () => {
    expect(tapIntent(10, 400, ctx('pages', 'vertical'))).toEqual(TOGGLE);
    expect(tapIntent(10, 400, ctx('pages', 'rtl', true))).toEqual(TOGGLE);
  });

  it('chapters: the sides do nothing (no edge taps), only the middle band toggles', () => {
    for (const mode of ['rtl', 'ltr', 'vertical'] as const) {
      expect(tapIntent(100, 1000, ctx('chapters', mode))).toBeNull();
      expect(tapIntent(900, 1000, ctx('chapters', mode))).toBeNull();
      expect(tapIntent(500, 1000, ctx('chapters', mode))).toEqual(TOGGLE);
    }
    // the band is per viewport: 25..75 for chapters, 30..70 for pages
    expect(tapIntent(260, 1000, ctx('chapters', 'ltr'))).toEqual(TOGGLE);
    expect(tapIntent(260, 1000, ctx('pages', 'ltr'))).toEqual(PREV);
  });

  it('an unknown width counts as the centre', () => {
    expect(tapIntent(0, 0, ctx('pages', 'rtl'))).toEqual(TOGGLE);
    expect(tapIntent(0, 0, ctx('chapters', 'ltr'))).toEqual(TOGGLE);
  });
});

describe('direction support', () => {
  it('a source that does not honor the direction behaves as ltr', () => {
    const plain = createInputContext(
      { kind: 'chapters', capabilities: { ...chapters.capabilities, honorsDirection: false } },
      'rtl',
    );
    expect(effectiveMode(plain)).toBe('ltr');
    expect(keyIntent('ArrowRight', plain)).toEqual(NEXT);
    expect(swipeIntent(-120, 0, plain)).toEqual(NEXT);
  });

  it('both built-in sources honor it', () => {
    expect(pages.capabilities.honorsDirection).toBe(true);
    expect(chapters.capabilities.honorsDirection).toBe(true);
  });

  it('scroll fractions: page 90%, line 10%, signed', () => {
    expect(scrollFraction({ type: 'scrollPage', sign: 1 })).toBe(0.9);
    expect(scrollFraction({ type: 'scrollPage', sign: -1 })).toBe(-0.9);
    expect(scrollFraction({ type: 'scrollLine', sign: 1 })).toBe(0.1);
    expect(scrollFraction(NEXT)).toBe(0);
  });
});
