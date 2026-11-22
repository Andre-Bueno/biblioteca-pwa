import { describe, expect, it } from 'vitest';
import {
  STRIP_AHEAD,
  STRIP_BEHIND,
  locateInStrip,
  measureFrameHeight,
  scrollTopForPosition,
  stripWindow,
} from '../../src/features/reader/epub/strip';

const BLOCKS = [
  { top: 0, height: 1000 },
  { top: 1000, height: 500 },
  { top: 1500, height: 2000 },
];

describe('stripWindow', () => {
  it('keeps a small window around the current chapter', () => {
    expect(stripWindow(50, 167)).toEqual({ from: 50 - STRIP_BEHIND, to: 50 + STRIP_AHEAD });
  });
  it('never mounts the whole book', () => {
    const { from, to } = stripWindow(80, 167);
    expect(to - from + 1).toBeLessThanOrEqual(STRIP_BEHIND + STRIP_AHEAD + 1);
  });
  it('clamps at the edges and handles odd input', () => {
    expect(stripWindow(0, 167)).toEqual({ from: 0, to: STRIP_AHEAD });
    expect(stripWindow(166, 167)).toEqual({ from: 166 - STRIP_BEHIND, to: 166 });
    expect(stripWindow(999, 3)).toEqual({ from: 2 - STRIP_BEHIND, to: 2 });
    expect(stripWindow(0, 0).to).toBeLessThan(stripWindow(0, 0).from);
    expect(stripWindow(Number.NaN, 5).from).toBe(0);
  });
});

describe('locateInStrip', () => {
  it('finds the chapter under the top edge and the offset in it', () => {
    expect(locateInStrip(0, BLOCKS)).toEqual({ chapter: 0, bp: 0 });
    expect(locateInStrip(500, BLOCKS)).toEqual({ chapter: 0, bp: 5000 });
    expect(locateInStrip(1000, BLOCKS)).toEqual({ chapter: 1, bp: 0 });
    expect(locateInStrip(1250, BLOCKS)).toEqual({ chapter: 1, bp: 5000 });
    expect(locateInStrip(2500, BLOCKS)).toEqual({ chapter: 2, bp: 5000 });
  });
  it('stays in range past the end and for empty or invalid input', () => {
    expect(locateInStrip(99999, BLOCKS)).toEqual({ chapter: 2, bp: 9999 });
    expect(locateInStrip(10, [])).toEqual({ chapter: 0, bp: 0 });
    expect(locateInStrip(Number.NaN, BLOCKS)).toEqual({ chapter: 0, bp: 0 });
    expect(locateInStrip(5, [{ top: 0, height: 0 }])).toEqual({ chapter: 0, bp: 0 });
  });
  it('round-trips with scrollTopForPosition', () => {
    for (const [chapter, bp] of [
      [0, 0],
      [1, 2500],
      [2, 9000],
    ] as const) {
      const block = BLOCKS[chapter]!;
      expect(locateInStrip(scrollTopForPosition(block, bp), BLOCKS)).toEqual({ chapter, bp });
    }
  });
});

describe('measureFrameHeight', () => {
  it('uses the content height and falls back to scrollHeight', () => {
    const root = { offsetHeight: 1234.2, scrollHeight: 5000 };
    expect(measureFrameHeight({ documentElement: root } as unknown as Document)).toBe(1235);
    const noBox = { offsetHeight: 0, scrollHeight: 900 };
    expect(measureFrameHeight({ documentElement: noBox } as unknown as Document)).toBe(900);
    const none = { offsetHeight: 0, scrollHeight: 0 };
    expect(measureFrameHeight({ documentElement: none } as unknown as Document)).toBe(0);
  });
});
