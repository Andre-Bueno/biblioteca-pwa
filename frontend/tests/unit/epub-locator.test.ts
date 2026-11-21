/* eslint-disable security/detect-non-literal-fs-filename -- test walks our own src tree */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  BP_MAX,
  bookPercent,
  bpFromScroll,
  clampChapter,
  decodeLocator,
  encodeLocator,
  isCenterTap,
  parseGotoHref,
  readerKeyAction,
  scrollTopFromBp,
  stepFontScale,
  swipeChapterStep,
} from '../../src/features/reader-epub/locator';
import { bookChapterUrl } from '../../src/shared/items';
import { normalizePreferences } from '../../src/shared/preferences';

describe('book locator (chapter * 10000 + offset in basis points)', () => {
  it('encodes and decodes', () => {
    expect(encodeLocator(0, 0)).toBe(0);
    expect(encodeLocator(3, 4200)).toBe(34200);
    expect(decodeLocator(34200)).toEqual({ chapter: 3, bp: 4200 });
    expect(decodeLocator(9999)).toEqual({ chapter: 0, bp: 9999 });
  });

  it('keeps the offset inside 0..9999 so it never spills into the next chapter', () => {
    expect(encodeLocator(2, 12000)).toBe(2 * 10000 + BP_MAX);
    expect(encodeLocator(2, -5)).toBe(20000);
    expect(encodeLocator(2, Number.NaN)).toBe(20000);
  });

  it('decodes garbage as the start of the book', () => {
    expect(decodeLocator(null)).toEqual({ chapter: 0, bp: 0 });
    expect(decodeLocator(-4)).toEqual({ chapter: 0, bp: 0 });
    expect(decodeLocator(Number.NaN)).toEqual({ chapter: 0, bp: 0 });
  });

  it('clamps the chapter to the book', () => {
    expect(clampChapter(7, 3)).toBe(2);
    expect(clampChapter(-1, 3)).toBe(0);
    expect(clampChapter(1, 0)).toBe(0);
  });

  it('converts scroll to basis points and back', () => {
    expect(bpFromScroll(0, 5000, 1000)).toBe(0);
    expect(bpFromScroll(4000, 5000, 1000)).toBe(BP_MAX); // bottom
    expect(bpFromScroll(2000, 5000, 1000)).toBe(5000);
    expect(bpFromScroll(10, 800, 1000)).toBe(0); // document shorter than the screen
    expect(scrollTopFromBp(5000, 5000, 1000)).toBeCloseTo(2000.2, 0);
    expect(scrollTopFromBp(BP_MAX, 5000, 1000)).toBe(4000);
    expect(scrollTopFromBp(5000, 800, 1000)).toBe(0);
  });

  it('estimates the percent of the whole book', () => {
    expect(bookPercent(0, 0, 4)).toBe(0);
    expect(bookPercent(2, 5000, 4)).toBe(63);
    expect(bookPercent(3, BP_MAX, 4)).toBe(100);
    expect(bookPercent(0, 0, 0)).toBe(0);
  });
});

describe('internal links', () => {
  it('parses only the rewritten ?goto= form', () => {
    expect(parseGotoHref('?goto=2')).toEqual({ index: 2, anchor: null });
    expect(parseGotoHref('?goto=12#cap%201')).toEqual({ index: 12, anchor: 'cap 1' });
    expect(parseGotoHref('?goto=3#')).toEqual({ index: 3, anchor: null });
  });

  it('rejects everything else', () => {
    for (const href of [
      null,
      '',
      '#a',
      'https://exemplo.com/?goto=1',
      'javascript:alert(1)',
      '?goto=abc',
      '?goto=-1',
      '?goto=1234567',
      '?goto=',
      '/x?goto=1',
    ]) {
      expect(parseGotoHref(href)).toBeNull();
    }
  });

  it('survives a malformed escape in the anchor', () => {
    expect(parseGotoHref('?goto=1#%E0%A4%A')).toEqual({ index: 1, anchor: '%E0%A4%A' });
  });
});

describe('settings and input helpers', () => {
  it('font scale moves in steps of 10 inside 80..200', () => {
    expect(stepFontScale(100, 1)).toBe(110);
    expect(stepFontScale(100, -1)).toBe(90);
    expect(stepFontScale(200, 1)).toBe(200);
    expect(stepFontScale(80, -1)).toBe(80);
    expect(stepFontScale(85, -1)).toBe(80);
  });

  it('maps keys', () => {
    expect(readerKeyAction('ArrowRight')).toBe('chapter-next');
    expect(readerKeyAction('ArrowLeft')).toBe('chapter-prev');
    expect(readerKeyAction('PageDown')).toBe('page-down');
    expect(readerKeyAction('PageUp')).toBe('page-up');
    expect(readerKeyAction('Home')).toBe('top');
    expect(readerKeyAction('End')).toBe('bottom');
    expect(readerKeyAction('x')).toBeNull();
  });

  it('swipes only count when clearly horizontal', () => {
    expect(swipeChapterStep(-120, 10)).toBe('chapter-next');
    expect(swipeChapterStep(120, -10)).toBe('chapter-prev');
    expect(swipeChapterStep(-120, 90)).toBeNull();
    expect(swipeChapterStep(-40, 0)).toBeNull();
  });

  it('only the middle of the screen toggles the controls', () => {
    expect(isCenterTap(500, 1000)).toBe(true);
    expect(isCenterTap(100, 1000)).toBe(false);
    expect(isCenterTap(900, 1000)).toBe(false);
  });
});

describe('chapter URL and preferences from the network', () => {
  it('builds the iframe src from validated values only', () => {
    expect(bookChapterUrl('a b', 2, 'sepia', 130)).toBe(
      '/api/v1/items/a%20b/book/chapters/2?theme=sepia&size=130',
    );
    expect(bookChapterUrl('x', -3, 'javascript', 9999)).toBe(
      '/api/v1/items/x/book/chapters/0?theme=auto&size=200',
    );
    expect(bookChapterUrl('x', 1.9, 'dark', 3)).toBe(
      '/api/v1/items/x/book/chapters/1?theme=dark&size=80',
    );
    expect(bookChapterUrl('x', 0, 'light', Number.NaN)).toContain('size=100');
  });

  it('normalizes the new preference fields and defaults invalid ones', () => {
    expect(
      normalizePreferences({
        theme: 'dark',
        reading_direction: 'ltr',
        book_font_scale: 150,
        book_theme: 'sepia',
      }),
    ).toEqual({
      theme: 'dark',
      reading_direction: 'ltr',
      book_font_scale: 150,
      book_theme: 'sepia',
    });
    const bad = normalizePreferences({ book_font_scale: 500, book_theme: 'neon' });
    expect(bad.book_font_scale).toBe(100);
    expect(bad.book_theme).toBe('auto');
    expect(normalizePreferences({ book_font_scale: '120' }).book_font_scale).toBe(100);
    expect(normalizePreferences(undefined).book_theme).toBe('auto'); // older server
  });
});

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

describe('EPUB reader source guards', () => {
  const files = sources('src/features/reader-epub');

  it('never injects HTML into the app', () => {
    for (const file of files) {
      const text = readFileSync(file, 'utf8');
      expect(text, file).not.toMatch(
        /dangerouslySetInnerHTML|innerHTML|outerHTML|insertAdjacentHTML/,
      );
    }
  });

  it('every sandbox attribute is exactly allow-same-origin', () => {
    const found: string[] = [];
    let iframes = 0;
    for (const file of files) {
      const text = readFileSync(file, 'utf8');
      iframes += (text.match(/<iframe\b/g) ?? []).length;
      for (const match of text.matchAll(/sandbox=(?:"([^"]*)"|\{([^}]*)\})/g)) {
        found.push(match[1] ?? match[2] ?? '');
      }
    }
    // Two iframes: the single chapter (EpubReaderPage) and each strip chapter (EpubStrip).
    expect(found).toEqual(['allow-same-origin', 'allow-same-origin']);
    // No iframe may exist without its own sandbox attribute.
    expect(iframes).toBe(found.length);
  });
});
