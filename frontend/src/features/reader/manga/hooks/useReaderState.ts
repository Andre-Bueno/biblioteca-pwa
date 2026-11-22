import { useCallback, useEffect, useState } from 'react';
import type { Item } from '../../../../shared/items';
import { usePreferences } from '../../../../shared/preferences';
import { useProgressSaver } from '../../../../shared/progress';
import { clampPage, keyAction, type ReaderMode, type Step } from '../navigation';
import { usePagePreload } from './usePagePreload';

interface Params {
  item: Item;
  savedLocator: number | null;
}

/** All reader behaviour: page, mode, zoom, controls, keyboard, preload and progress saving. */
export function useReaderState({ item, savedLocator }: Params) {
  const pageCount = item.page_count ?? 0;
  const { preferences } = usePreferences();
  const saver = useProgressSaver(item.id);

  const [initialPage] = useState(() => clampPage(savedLocator ?? 0, pageCount));
  const [page, setPage] = useState(initialPage);
  const [modeOverride, setModeOverride] = useState<ReaderMode | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);
  // Vertical mode scrolls to a page when asked (slider, Home/End, mode switch).
  const [jump, setJump] = useState({ page: initialPage, nonce: 0 });

  const mode: ReaderMode = modeOverride ?? preferences.reading_direction;

  const { setBaseline, report } = saver;
  useEffect(() => {
    setBaseline(savedLocator);
    // First visit: registers "page 1" so the item shows up in "continue reading".
    if (pageCount > 0) report(initialPage);
  }, [setBaseline, report, savedLocator, pageCount, initialPage]);

  const goTo = useCallback(
    (target: number) => {
      const next = clampPage(target, pageCount);
      setPage(next);
      setZoomed(false);
      setJump((previous) => ({ page: next, nonce: previous.nonce + 1 }));
      report(next);
    },
    [pageCount, report],
  );

  /** Page reported by the scroll position in vertical mode (no scrolling back). */
  const onVisiblePage = useCallback(
    (visible: number) => {
      const next = clampPage(visible, pageCount);
      setPage(next);
      report(next);
    },
    [pageCount, report],
  );

  const step = useCallback(
    (direction: Step) => goTo(page + (direction === 'next' ? 1 : -1)),
    [goTo, page],
  );

  const changeMode = useCallback(
    (next: ReaderMode) => {
      setModeOverride(next);
      setZoomed(false);
      setJump((previous) => ({ page, nonce: previous.nonce + 1 }));
    },
    [page],
  );

  const toggleControls = useCallback(() => setControlsVisible((value) => !value), []);
  const toggleZoom = useCallback(() => setZoomed((value) => !value), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === 'm' || event.key === 'M') {
        // Keyboard way to bring the controls back (no tap needed).
        if (target instanceof HTMLButtonElement) return;
        setControlsVisible((value) => !value);
        return;
      }
      const action = keyAction(event.key, mode);
      if (!action) return;
      event.preventDefault();
      if (action === 'first') goTo(0);
      else if (action === 'last') goTo(pageCount - 1);
      else step(action);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mode, goTo, step, pageCount]);

  usePagePreload(item.id, page, pageCount, mode !== 'vertical');

  return {
    item,
    pageCount,
    page,
    mode,
    zoomed,
    controlsVisible,
    jump,
    saveStatus: saver.status,
    goTo,
    step,
    onVisiblePage,
    changeMode,
    toggleControls,
    toggleZoom,
  };
}

export type ReaderState = ReturnType<typeof useReaderState>;
