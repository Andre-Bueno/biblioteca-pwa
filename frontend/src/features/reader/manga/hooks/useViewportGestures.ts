import { useCallback, useEffect, useRef, type PointerEvent } from 'react';
import { TAP_MAX_MOVE_PX, swipeStep, tapZone, type ReaderMode, type Step } from '../navigation';

export const DOUBLE_TAP_MS = 280;

interface Options {
  mode: ReaderMode;
  zoomed: boolean;
  onStep: (step: Step) => void;
  onCenterTap: () => void;
  onDoubleTap: () => void;
}

/**
 * Touch/mouse gestures on the page area: edge taps turn the page, a horizontal swipe turns the
 * page, a centre tap toggles the controls and a double tap in the centre toggles zoom. Page-turn
 * taps are immediate (no double-tap wait); only the centre tap waits to tell single from double.
 */
export function useViewportGestures({ mode, zoomed, onStep, onCenterTap, onDoubleTap }: Options) {
  const start = useRef<{ x: number; y: number } | null>(null);
  const pendingCenter = useRef<ReturnType<typeof setTimeout> | null>(null);
  const zoomEnabled = mode !== 'vertical';

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

      if (!zoomed) {
        const step = swipeStep(dx, dy, mode);
        if (step) {
          onStep(step);
          return;
        }
      }
      if (Math.abs(dx) > TAP_MAX_MOVE_PX || Math.abs(dy) > TAP_MAX_MOVE_PX) return; // a drag

      const rect = event.currentTarget.getBoundingClientRect();
      const width = rect.width || window.innerWidth;
      const zone = tapZone(event.clientX - rect.left, width, mode, zoomed);
      if (zone !== 'center') {
        onStep(zone);
        return;
      }
      if (!zoomEnabled) {
        onCenterTap();
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
        onCenterTap();
      }, DOUBLE_TAP_MS);
    },
    [mode, zoomed, zoomEnabled, onStep, onCenterTap, onDoubleTap],
  );

  return { onPointerDown, onPointerUp, onPointerCancel };
}
