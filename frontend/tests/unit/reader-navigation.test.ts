import { describe, expect, it } from 'vitest';
import { keyAction, swipeStep, tapZone } from '../../src/features/reader/manga/navigation';

describe('tapZone', () => {
  it('rtl: left edge goes forward, right edge goes back', () => {
    expect(tapZone(10, 400, 'rtl', false)).toBe('next');
    expect(tapZone(390, 400, 'rtl', false)).toBe('prev');
  });
  it('ltr: right edge goes forward, left edge goes back', () => {
    expect(tapZone(390, 400, 'ltr', false)).toBe('next');
    expect(tapZone(10, 400, 'ltr', false)).toBe('prev');
  });
  it('the middle is the controls zone in every mode', () => {
    for (const mode of ['rtl', 'ltr', 'vertical'] as const) {
      expect(tapZone(200, 400, mode, false)).toBe('center');
    }
  });
  it('vertical mode and zoomed pages have no page-turn zones', () => {
    expect(tapZone(10, 400, 'vertical', false)).toBe('center');
    expect(tapZone(10, 400, 'rtl', true)).toBe('center');
  });
});

describe('swipeStep', () => {
  it('rtl: swiping right brings the next page', () => {
    expect(swipeStep(120, 5, 'rtl')).toBe('next');
    expect(swipeStep(-120, 5, 'rtl')).toBe('prev');
  });
  it('ltr: swiping left brings the next page', () => {
    expect(swipeStep(-120, 5, 'ltr')).toBe('next');
    expect(swipeStep(120, 5, 'ltr')).toBe('prev');
  });
  it('ignores short, mostly vertical and vertical-mode gestures', () => {
    expect(swipeStep(30, 0, 'rtl')).toBeNull();
    expect(swipeStep(80, 90, 'rtl')).toBeNull();
    expect(swipeStep(200, 0, 'vertical')).toBeNull();
  });
});

describe('keyAction', () => {
  it('maps arrows by direction', () => {
    expect(keyAction('ArrowLeft', 'rtl')).toBe('next');
    expect(keyAction('ArrowRight', 'rtl')).toBe('prev');
    expect(keyAction('ArrowLeft', 'ltr')).toBe('prev');
    expect(keyAction('ArrowRight', 'ltr')).toBe('next');
  });
  it('Home/End always jump; arrows are left to native scroll in vertical mode', () => {
    expect(keyAction('Home', 'vertical')).toBe('first');
    expect(keyAction('End', 'rtl')).toBe('last');
    expect(keyAction('ArrowDown', 'vertical')).toBeNull();
    expect(keyAction('a', 'rtl')).toBeNull();
  });
});
