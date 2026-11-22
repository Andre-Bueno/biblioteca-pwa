import { useCallback, useEffect, useState } from 'react';
import { useAutoHideControls } from '../../../shared/hooks';
import { usePreferences, type ReadingDirection } from '../../../shared/preferences';

export type Panel = 'none' | 'toc' | 'settings';
export type PrefsWarning = 'load' | 'save' | null;

/** Delay before a dragged slider opens its unit (a pause means the user chose). */
export const SLIDER_DELAY_MS = 350;

const TEXT_FIELDS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

/**
 * Everything around the content that every reader shares: bars (auto-hide on touch, toggle), the
 * open panel (table of contents or settings), the slider value while it is being dragged, the
 * preference warnings and the keys that belong to the chrome (`m`, Esc).
 */
export function useReaderChrome() {
  const { preferences, saveFailed, loadFailed, update } = usePreferences();
  const [panel, setPanel] = useState<Panel>('none');
  // Slider: the value the thumb shows while dragging (null = it follows the current unit).
  const [pending, setPending] = useState<number | null>(null);
  // Touch: full screen on open, tap toggles, hides after a few idle seconds (not while a panel
  // is open or the slider is being dragged). Mouse: the bars stay until toggled.
  const [dragging, setDragging] = useState(false); // a finger/mouse is held on the slider
  const controls = useAutoHideControls({
    paused: panel !== 'none' || pending !== null || dragging,
  });

  const { toggle, keepAlive, visible } = controls;
  const openPanel = useCallback((next: Exclude<Panel, 'none'>) => setPanel(next), []);
  const closePanel = useCallback(() => setPanel('none'), []);

  /**
   * First look at a key press. Returns true when the chrome took it or when the reader must
   * ignore it (modifiers, an open panel that owns the keyboard, a text field, a focused button
   * for `m`); the reader handles its own keys only when this returns false.
   */
  const handleKey = useCallback(
    (event: KeyboardEvent): boolean => {
      if (event.metaKey || event.ctrlKey || event.altKey) return true;
      if (event.key === 'Escape') {
        if (panel !== 'none') setPanel('none');
        return true;
      }
      if (panel !== 'none') return true;
      const tag = (event.target as { tagName?: string } | null)?.tagName ?? '';
      if (TEXT_FIELDS.has(tag)) return true;
      if (event.key === 'm' || event.key === 'M') {
        // Keyboard way to bring the bars back (no tap needed).
        if (tag !== 'BUTTON') toggle();
        return true;
      }
      return false;
    },
    [panel, toggle],
  );

  // Reading mode: one rule for every format. It is a saved preference and applies at once.
  const mode: ReadingDirection = preferences.reading_direction;
  const changeMode = useCallback(
    (next: ReadingDirection) => {
      if (next !== mode) void update({ reading_direction: next });
    },
    [mode, update],
  );

  /** Spread on the slider: the bars stay up for as long as it is held. */
  const dragHandlers = {
    onPointerDown: () => setDragging(true),
    onPointerUp: () => setDragging(false),
    onPointerCancel: () => setDragging(false),
    onBlur: () => setDragging(false),
  };

  const prefsWarning: PrefsWarning = loadFailed ? 'load' : saveFailed ? 'save' : null;

  return {
    visible,
    toggle,
    keepAlive,
    panel,
    openPanel,
    closePanel,
    pending,
    setPending,
    handleKey,
    mode,
    changeMode,
    dragHandlers,
    prefsWarning,
  };
}

export type ReaderChrome = ReturnType<typeof useReaderChrome>;

interface SliderOptions {
  chrome: Pick<ReaderChrome, 'pending' | 'setPending'>;
  /** The unit being shown. */
  current: number;
  /** Opens the unit chosen with the slider. */
  commit: (unit: number) => void;
  /** 0 opens at once (cheap units, like an image); otherwise waits for the user to pause. */
  delayMs: number;
}

/** Slider over the units: value shown while dragging, unit opened immediately or after a pause. */
export function useUnitSlider({ chrome, current, commit, delayMs }: SliderOptions) {
  const { pending, setPending } = chrome;

  useEffect(() => {
    if (pending === null || delayMs <= 0) return undefined;
    const timer = setTimeout(() => {
      if (pending === current) setPending(null);
      else commit(pending);
    }, delayMs);
    return () => clearTimeout(timer);
  }, [pending, current, delayMs, commit, setPending]);

  const onChange = useCallback(
    (unit: number) => {
      if (delayMs <= 0) commit(unit);
      else setPending(unit);
    },
    [delayMs, commit, setPending],
  );

  return { value: pending ?? current, onChange };
}

export type UnitSlider = ReturnType<typeof useUnitSlider>;
