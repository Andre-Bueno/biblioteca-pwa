import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AUTO_HIDE_MS, useAutoHideControls } from '../../src/shared/hooks';

function stubTouch(touch: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: touch && query.includes('pointer: coarse'),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    })),
  );
}

describe('useAutoHideControls', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('on touch: starts hidden, a tap shows, and it hides itself after the delay', () => {
    stubTouch(true);
    const { result } = renderHook(() => useAutoHideControls());
    expect(result.current.visible).toBe(false);
    act(() => result.current.toggle());
    expect(result.current.visible).toBe(true);
    act(() => {
      vi.advanceTimersByTime(AUTO_HIDE_MS - 1);
    });
    expect(result.current.visible).toBe(true);
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(result.current.visible).toBe(false);
  });

  it('keepAlive restarts the wait; paused keeps the controls up until released', () => {
    stubTouch(true);
    const { result, rerender } = renderHook(({ paused }) => useAutoHideControls({ paused }), {
      initialProps: { paused: false },
    });
    act(() => result.current.show());
    act(() => {
      vi.advanceTimersByTime(AUTO_HIDE_MS - 500);
    });
    act(() => result.current.keepAlive());
    act(() => {
      vi.advanceTimersByTime(AUTO_HIDE_MS - 500);
    });
    expect(result.current.visible).toBe(true);

    rerender({ paused: true });
    act(() => {
      vi.advanceTimersByTime(AUTO_HIDE_MS * 3);
    });
    expect(result.current.visible).toBe(true);
    rerender({ paused: false });
    act(() => {
      vi.advanceTimersByTime(AUTO_HIDE_MS + 1);
    });
    expect(result.current.visible).toBe(false);
  });

  it('with a mouse: starts visible and never hides on a timer', () => {
    stubTouch(false);
    const { result } = renderHook(() => useAutoHideControls());
    expect(result.current.visible).toBe(true);
    act(() => {
      vi.advanceTimersByTime(AUTO_HIDE_MS * 5);
    });
    expect(result.current.visible).toBe(true);
    act(() => result.current.toggle());
    expect(result.current.visible).toBe(false);
  });
});
