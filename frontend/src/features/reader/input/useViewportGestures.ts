import { useCallback, useEffect, useRef, type PointerEvent } from 'react';
import {
  swipeIntent,
  tapIntent,
  viewportInput,
  type InputContext,
  type ReaderIntent,
} from './intents';

export const DOUBLE_TAP_MS = 280;

interface Options {
  input: InputContext;
  onIntent: (intent: ReaderIntent) => void;
  onDoubleTap: () => void;
}

/**
 * Touch/mouse gestures on an image viewport: edge taps and a horizontal swipe become intents
 * (by direction and source), a centre tap toggles the controls and a double tap in the centre
 * toggles zoom. Page-turn taps are immediate (no double-tap wait); only the centre tap waits to
 * tell single from double.
 */
export function useViewportGestures({ input, onIntent, onDoubleTap }: Options) {
  const start = useRef<{ x: number; y: number } | null>(null);
  const pendingCenter = useRef<ReturnType<typeof setTimeout> | null>(null);
  const zoomEnabled = input.mode !== 'vertical' && input.source.capabilities.zoomToggle;

  useEffect(
    () => () => {
      if (pendingCenter.current !== null) clearTimeout(pendingCenter.current);
    },
    [],
  );

  const onPointerDown = useCallback((event: PointerEvent<HTMLElement>) => {
    start.current = { x: event.clientX, y: event.clientY };
  }, []);

  const onPointerCancel = useCallback(() => {
    start.current = null; // the browser took the gesture over (native scroll)
  }, []);

  const onPointerUp = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const origin = start.current;
      start.current = null;
      if (!origin) return;
      const dx = event.clientX - origin.x;
      const dy = event.clientY - origin.y;

      const swipe = swipeIntent(dx, dy, input);
      if (swipe) {
        onIntent(swipe);
        return;
      }
      const { tapMaxMovePx } = viewportInput(input);
      if (Math.abs(dx) > tapMaxMovePx || Math.abs(dy) > tapMaxMovePx) return; // a drag

      const rect = event.currentTarget.getBoundingClientRect();
      const width = rect.width || window.innerWidth;
      const tap = tapIntent(event.clientX - rect.left, width, input);
      if (!tap) return;
      if (tap.type !== 'toggleChrome') {
        onIntent(tap);
        return;
      }
      if (!zoomEnabled) {
        onIntent(tap);
        return;
      }
      if (pendingCenter.current !== null) {
        clearTimeout(pendingCenter.current);
        pendingCenter.current = null;
        onDoubleTap();
        return;
      }
      pendingCenter.current = setTimeout(() => {
        pendingCenter.current = null;
        onIntent(tap);
      }, DOUBLE_TAP_MS);
    },
    [input, zoomEnabled, onIntent, onDoubleTap],
  );

  return { onPointerDown, onPointerUp, onPointerCancel };
}
