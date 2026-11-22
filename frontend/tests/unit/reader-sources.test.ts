import { describe, expect, it } from 'vitest';
import { createBookChaptersSource } from '../../src/features/reader/sources/chaptersSource';
import { createImagePagesSource, pagesCodec } from '../../src/features/reader/sources/pagesSource';
import { selectSource } from '../../src/features/reader/sources/selectSource';

const book = {
  chapters: [
    { index: 0, title: 'Intro' },
    { index: 1, title: '' },
    { index: 2, title: 'End' },
  ],
  toc: [
    { title: 'Intro', index: 0, anchor: null },
    { title: 'Part', index: 2, anchor: 'p1' },
  ],
};

describe('ImagePagesSource', () => {
  const source = createImagePagesSource(10);

  it('describes a pages source', () => {
    expect(source.kind).toBe('pages');
    expect(source.unitCount).toBe(10);
    expect(source.toc).toBeUndefined();
    expect(source.capabilities).toEqual({
      textSettings: false,
      zoomToggle: true,
      edgeTapsStep: true,
      honorsDirection: true,
    });
  });

  it('decode: the locator is the 0-based page; saved 5 stays page 5', () => {
    expect(source.codec.decode(5)).toEqual({ unit: 5, bp: 0 });
    expect(source.codec.decode(0)).toEqual({ unit: 0, bp: 0 });
    expect(source.codec.decode(12345)).toEqual({ unit: 12345, bp: 0 });
  });

  it('decode: hostile or missing values become page 0', () => {
    for (const bad of [null, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(source.codec.decode(bad)).toEqual({ unit: 0, bp: 0 });
    }
    expect(source.codec.decode(3.9)).toEqual({ unit: 3, bp: 0 });
  });

  it('encode: ignores the offset and never goes negative', () => {
    expect(source.codec.encode(5, 0)).toBe(5);
    expect(source.codec.encode(5, 9999)).toBe(5);
    expect(source.codec.encode(-3, 0)).toBe(0);
    expect(source.codec.encode(Number.NaN, 0)).toBe(0);
    expect(source.codec.encode(4.7, 0)).toBe(4);
  });

  it('round-trips', () => {
    for (const page of [0, 1, 5, 9]) {
      expect(source.codec.decode(source.codec.encode(page, 0)).unit).toBe(page);
    }
  });

  it('clampUnit keeps the page inside the range', () => {
    expect(source.clampUnit(-4)).toBe(0);
    expect(source.clampUnit(4)).toBe(4);
    expect(source.clampUnit(99)).toBe(9);
    expect(source.clampUnit(Number.NaN)).toBe(0);
    expect(createImagePagesSource(0).clampUnit(3)).toBe(0);
  });

  it('percent counts the current page as read', () => {
    expect(source.codec.percent(0, 0, 10)).toBe(10);
    expect(source.codec.percent(4, 0, 10)).toBe(50);
    expect(source.codec.percent(9, 0, 10)).toBe(100);
    expect(source.codec.percent(50, 0, 10)).toBe(100);
    expect(source.codec.percent(0, 0, 0)).toBe(0);
    expect(pagesCodec.percent(-5, 0, 4)).toBe(25);
  });

  it('titles are 1-based and clamped; bad counts become 0 units', () => {
    expect(source.unitTitle(0)).toBe('Página 1');
    expect(source.unitTitle(99)).toBe('Página 10');
    expect(createImagePagesSource(Number.NaN).unitCount).toBe(0);
    expect(createImagePagesSource(-2).unitCount).toBe(0);
  });
});

describe('BookChaptersSource', () => {
  const source = createBookChaptersSource(book);

  it('describes a chapters source', () => {
    expect(source.kind).toBe('chapters');
    expect(source.unitCount).toBe(3);
    expect(source.capabilities).toEqual({
      textSettings: true,
      zoomToggle: false,
      edgeTapsStep: false,
      honorsDirection: true,
    });
  });

  it('maps the toc to units', () => {
    expect(source.toc).toEqual([
      { title: 'Intro', unit: 0, anchor: null },
      { title: 'Part', unit: 2, anchor: 'p1' },
    ]);
  });

  it('locator stays chapter * 10000 + bp', () => {
    expect(source.codec.encode(3, 2500)).toBe(32500);
    expect(source.codec.decode(32500)).toEqual({ unit: 3, bp: 2500 });
    expect(source.codec.decode(null)).toEqual({ unit: 0, bp: 0 });
    expect(source.codec.decode(-7)).toEqual({ unit: 0, bp: 0 });
    expect(source.codec.encode(2, 99999)).toBe(2 * 10000 + 9999);
  });

  it('percent follows the book formula', () => {
    expect(source.codec.percent(0, 0, 3)).toBe(0);
    expect(source.codec.percent(1, 5000, 4)).toBe(38);
    expect(source.codec.percent(2, 9999, 3)).toBe(100);
    expect(source.codec.percent(0, 0, 0)).toBe(0);
  });

  it('clampUnit and unitTitle', () => {
    expect(source.clampUnit(-1)).toBe(0);
    expect(source.clampUnit(9)).toBe(2);
    expect(source.unitTitle(0)).toBe('Intro');
    expect(source.unitTitle(1)).toBe('Capítulo 2');
    expect(source.unitTitle(50)).toBe('End');
  });

  it('handles an empty book', () => {
    const empty = createBookChaptersSource({ chapters: [], toc: [] });
    expect(empty.unitCount).toBe(0);
    expect(empty.clampUnit(4)).toBe(0);
    expect(empty.toc).toEqual([]);
  });
});

describe('selectSource', () => {
  it('book -> chapters', () => {
    const source = selectSource('book', { pageCount: 0, book });
    expect(source.kind).toBe('chapters');
    expect(source.unitCount).toBe(3);
  });

  it('book without structure -> empty chapters', () => {
    const source = selectSource('book', { pageCount: 7 });
    expect(source.kind).toBe('chapters');
    expect(source.unitCount).toBe(0);
  });

  it('manga and pdf -> pages', () => {
    for (const type of ['manga', 'pdf'] as const) {
      const source = selectSource(type, { pageCount: 20, book });
      expect(source.kind).toBe('pages');
      expect(source.unitCount).toBe(20);
    }
  });

  it('the same saved locator reads differently by item type', () => {
    expect(selectSource('manga', { pageCount: 20 }).codec.decode(5)).toEqual({ unit: 5, bp: 0 });
    expect(selectSource('book', { pageCount: 0, book }).codec.decode(5)).toEqual({
      unit: 0,
      bp: 5,
    });
    expect(selectSource('book', { pageCount: 0, book }).codec.decode(30000)).toEqual({
      unit: 3,
      bp: 0,
    });
  });
});
