import { useCallback, useEffect, useState } from 'react';

/** Phones and tablets: no hover, a finger as the main pointer. */
const TOUCH_QUERY = '(hover: none) and (pointer: coarse)';
export const AUTO_HIDE_MS = 4000;

export function isTouchPrimary(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(TOUCH_QUERY).matches
    : false;
}

interface Options {
  /** Keeps the controls up while true (open panel, slider being dragged). */
  paused?: boolean;
  delayMs?: number;
}

/**
 * Reader chrome (bars) visibility. On touch devices the reader opens in full screen (controls
 * hidden), a tap toggles them and they hide by themselves after `delayMs` without interaction
 * (`keepAlive` restarts the wait). On devices with a mouse the controls stay as they were
 * (visible until toggled) and nothing hides on a timer. The choice is made once, on mount.
 */
export function useAutoHideControls({ paused = false, delayMs = AUTO_HIDE_MS }: Options = {}) {
  const [auto] = useState(isTouchPrimary);
  const [visible, setVisible] = useState(!auto);
  const [activity, setActivity] = useState(0);

  const toggle = useCallback(() => setVisible((value) => !value), []);
  const show = useCallback(() => setVisible(true), []);
  const keepAlive = useCallback(() => setActivity((value) => value + 1), []);

  useEffect(() => {
    if (!auto || !visible || paused) return undefined;
    const timer = setTimeout(() => setVisible(false), delayMs);
    return () => clearTimeout(timer);
  }, [auto, visible, paused, delayMs, activity]);

  return { visible, auto, toggle, show, keepAlive };
}
