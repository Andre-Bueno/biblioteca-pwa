import { useCallback, useEffect, useState } from 'react';
import type { Item } from '../../../../shared/items';
import type { ReadingDirection } from '../../../../shared/preferences';
import type { ReaderNav } from '../../../../shared/series';
import { useReaderProgress } from '../../hooks/useReaderProgress';
import type { ReaderShellProps } from '../../shell/ReaderShell';
import { useReaderChrome, useUnitSlider } from '../../shell/useReaderChrome';
import type { ReaderSource, UnitPosition } from '../../sources';
import type { Step } from '../../shell/types';
import { keyAction } from '../navigation';
import { usePagePreload } from './usePagePreload';

interface Params {
  item: Item;
  source: ReaderSource;
  nav: ReaderNav;
  savedLocator: number | null;
  savedPosition: UnitPosition;
}

/** Behaviour of the page reader: page, mode, zoom, keyboard, preload and what the shell shows. */
export function useReaderState({ item, source, nav, savedLocator, savedPosition }: Params) {
  const pageCount = source.unitCount;
  const chrome = useReaderChrome();
  const { reportPosition, saveStatus } = useReaderProgress(
    item.id,
    source,
    savedLocator,
    savedPosition,
  );

  const [initialPage] = useState(savedPosition.unit);
  const [page, setPage] = useState(initialPage);
  const [zoomed, setZoomed] = useState(false);
  // Vertical mode scrolls to a page when asked (slider, Home/End, mode switch).
  const [jump, setJump] = useState({ page: initialPage, nonce: 0 });

  const { mode, changeMode: saveMode } = chrome;

  const goTo = useCallback(
    (target: number) => {
      const next = source.clampUnit(target);
      setPage(next);
      setZoomed(false);
      setJump((previous) => ({ page: next, nonce: previous.nonce + 1 }));
      reportPosition(next);
    },
    [source, reportPosition],
  );

  /** Page reported by the scroll position in vertical mode (no scrolling back). */
  const onVisiblePage = useCallback(
    (visible: number) => {
      const next = source.clampUnit(visible);
      setPage(next);
      reportPosition(next);
    },
    [source, reportPosition],
  );

  const step = useCallback(
    (direction: Step) => goTo(page + (direction === 'next' ? 1 : -1)),
    [goTo, page],
  );

  const changeMode = useCallback(
    (next: ReadingDirection) => {
      setZoomed(false);
      setJump((previous) => ({ page, nonce: previous.nonce + 1 })); // keep the page in the new mode
      saveMode(next);
    },
    [page, saveMode],
  );

  const toggleZoom = useCallback(() => setZoomed((value) => !value), []);

  const handleChromeKey = chrome.handleKey;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (handleChromeKey(event)) return;
      const action = keyAction(event.key, mode);
      if (!action) return;
      event.preventDefault();
      if (action === 'first') goTo(0);
      else if (action === 'last') goTo(pageCount - 1);
      else step(action);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleChromeKey, mode, goTo, step, pageCount]);

  usePagePreload(item.id, page, pageCount, mode !== 'vertical');

  // Pages are cheap to open: the slider turns to the page as it moves.
  const slider = useUnitSlider({ chrome, current: page, commit: goTo, delayMs: 0 });

  const shell: ReaderShellProps = {
    title: item.title,
    source,
    nav,
    unit: page,
    percent: source.codec.percent(page, 0, pageCount),
    atEnd: pageCount > 0 && page >= pageCount - 1,
    mode,
    saveStatus,
    chrome,
    slider,
    onStep: step,
    onGoTo: goTo,
    onModeChange: changeMode,
    zoom: mode === 'vertical' ? null : { active: zoomed, toggle: toggleZoom },
    text: null,
  };

  return {
    item,
    pageCount,
    page,
    mode,
    zoomed,
    jump,
    goTo,
    step,
    onVisiblePage,
    toggleControls: chrome.toggle,
    toggleZoom,
    shell,
  };
}

export type ReaderState = ReturnType<typeof useReaderState>;
