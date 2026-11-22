import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { bookChapterUrl, type BookInfo, type Item } from '../../../../shared/items';
import { useAutoHideControls } from '../../../../shared/hooks';
import { usePreferences, type BookTheme } from '../../../../shared/preferences';
import { useProgressSaver } from '../../../../shared/progress';
import { useReaderNav } from '../../../../shared/series';
import {
  BP_MAX,
  bookPercent,
  clampChapter,
  decodeLocator,
  encodeLocator,
  readerKeyAction,
  stepFontScale,
} from '../locator';
import { useEpubFrame } from './useEpubFrame';
import { useEpubStrip, type StripJump } from './useEpubStrip';

interface Params {
  frameRef: RefObject<HTMLIFrameElement | null>;
  item: Item;
  book: BookInfo;
  savedLocator: number | null;
}

export type Panel = 'none' | 'toc' | 'settings';

/** From here on the chapter counts as "read to the end" (offers the next chapter). */
const END_BP = 9900;
const SLIDER_DELAY_MS = 350;

/** All behaviour of the EPUB reader: chapter, position, panels, preferences, keys and progress. */
export function useEpubReader({ frameRef, item, book, savedLocator }: Params) {
  const count = book.chapters.length;
  const { preferences, saveFailed, loadFailed, update } = usePreferences();
  const saver = useProgressSaver(item.id);
  const nav = useReaderNav(item);

  const [initial] = useState(() => {
    const decoded = decodeLocator(savedLocator);
    const chapter = clampChapter(decoded.chapter, count);
    return { chapter, bp: chapter === decoded.chapter ? decoded.bp : 0 };
  });
  const [chapter, setChapter] = useState(initial.chapter);
  const [bp, setBp] = useState(initial.bp);
  const [panel, setPanel] = useState<Panel>('none');
  // "Vertical" reading direction = continuous scroll through the chapters (same preference as the
  // manga strip). The page remounts the reader when it changes.
  const vertical = preferences.reading_direction === 'vertical';
  const [loading, setLoading] = useState(!vertical); // the strip loads per chapter
  const [loadFailedFrame, setLoadFailedFrame] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [sliderValue, setSliderValue] = useState<number | null>(null);
  // Touch: full screen on open, tap toggles, hides after a few idle seconds (not while a panel
  // is open or the slider is being dragged). Mouse: bars stay as before.
  const controls = useAutoHideControls({ paused: panel !== 'none' || sliderValue !== null });
  const controlsVisible = controls.visible;
  const toggleControls = controls.toggle;
  const [jump, setJump] = useState<StripJump>(() => ({
    chapter: initial.chapter,
    bp: initial.bp,
    nonce: 0,
  }));

  const positionRef = useRef(initial.bp);
  const shownRef = useRef({ chapter: initial.chapter, bp: initial.bp });
  const anchorRef = useRef<string | null>(null);
  const scrollApi = useRef<{ by: (f: number) => void; edge: (e: 'top' | 'bottom') => void } | null>(
    null,
  );

  const theme: BookTheme = preferences.book_theme;
  const fontScale = preferences.book_font_scale;
  const src = bookChapterUrl(item.id, chapter, theme, fontScale);

  const { setBaseline, report } = saver;
  useEffect(() => {
    setBaseline(savedLocator);
    // First visit: registers the book so it shows up in "continue reading".
    if (savedLocator === null && count > 0) report(encodeLocator(initial.chapter, initial.bp));
  }, [setBaseline, report, savedLocator, count, initial]);

  const goToChapter = useCallback(
    (target: number, anchor: string | null = null) => {
      const next = clampChapter(target, count);
      setPanel('none');
      setSliderValue(null);
      if (vertical) {
        // Continuous mode: scroll the strip to the chapter (anchors are not used here).
        positionRef.current = 0;
        shownRef.current = { chapter: next, bp: 0 };
        setBp(0);
        setChapter(next);
        setJump((value) => ({ chapter: next, bp: 0, nonce: value.nonce + 1 }));
        report(encodeLocator(next, 0));
        return;
      }
      if (next === chapter && !anchor) {
        scrollApi.current?.edge('top');
        return;
      }
      positionRef.current = 0;
      anchorRef.current = anchor;
      setBp(0);
      setLoadFailedFrame(false);
      setLoading(true);
      if (next === chapter) setReloadNonce((value) => value + 1); // same chapter, new anchor
      setChapter(next);
      report(encodeLocator(next, 0)); // the user moved: save the new position
    },
    [count, chapter, report, vertical],
  );

  const step = useCallback(
    (direction: 'chapter-prev' | 'chapter-next') => {
      const target = chapter + (direction === 'chapter-next' ? 1 : -1);
      if (target >= 0 && target < count) goToChapter(target);
    },
    [goToChapter, chapter, count],
  );

  const closePanel = useCallback(() => setPanel('none'), []);
  const openPanel = useCallback((next: Exclude<Panel, 'none'>) => setPanel(next), []);

  const handleKey = useCallback(
    (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === 'Escape') {
        if (panel !== 'none') setPanel('none');
        return;
      }
      if (panel !== 'none') return; // the open panel owns the keyboard
      const target = event.target as { tagName?: string } | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (event.key === 'm' || event.key === 'M') {
        if (tag === 'BUTTON') return;
        toggleControls();
        return;
      }
      const action = readerKeyAction(event.key);
      if (!action) return;
      event.preventDefault();
      if (action === 'chapter-prev' || action === 'chapter-next') step(action);
      else if (action === 'page-down') scrollApi.current?.by(0.9);
      else if (action === 'page-up') scrollApi.current?.by(-0.9);
      else if (action === 'line-down') scrollApi.current?.by(0.1);
      else if (action === 'line-up') scrollApi.current?.by(-0.1);
      else scrollApi.current?.edge(action === 'top' ? 'top' : 'bottom');
    },
    [panel, step, toggleControls],
  );

  const frame = useEpubFrame({
    frameRef,
    chapter,
    positionRef,
    anchorRef,
    callbacks: {
      onPosition: (loadedChapter, value, shouldReport) => {
        if (loadedChapter !== chapter) return; // late event of a document we left
        setBp(value);
        if (shouldReport) report(encodeLocator(loadedChapter, value));
      },
      onGoto: goToChapter,
      onToggleControls: toggleControls,
      onKey: handleKey,
      onSwipe: step,
      onLoaded: (ok) => {
        setLoading(false);
        setLoadFailedFrame(!ok);
      },
    },
  });

  const strip = useEpubStrip({
    enabled: vertical,
    chapter,
    count,
    initial,
    jump,
    callbacks: {
      onPosition: (stripChapter, value, shouldReport) => {
        // Re-render only on a real change (chapter, >= 1%, or crossing the "end" threshold).
        const last = shownRef.current;
        if (
          stripChapter !== last.chapter ||
          Math.abs(value - last.bp) >= 100 ||
          value >= END_BP !== last.bp >= END_BP
        ) {
          shownRef.current = { chapter: stripChapter, bp: value };
          setChapter(stripChapter);
          setBp(value);
        }
        if (shouldReport) report(encodeLocator(stripChapter, value));
      },
      onGoto: goToChapter,
      onToggleControls: toggleControls,
      onKey: handleKey,
    },
  });

  const scrollBy = vertical ? strip.scrollBy : frame.scrollBy;
  const scrollToEdge = vertical ? strip.scrollToEdge : frame.scrollToEdge;
  useEffect(() => {
    scrollApi.current = { by: scrollBy, edge: scrollToEdge };
  }, [scrollBy, scrollToEdge]);

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  // Slider: shows the value while dragging, opens the chapter once the user pauses.
  useEffect(() => {
    if (sliderValue === null) return undefined;
    const timer = setTimeout(() => {
      if (sliderValue === chapter) setSliderValue(null);
      else goToChapter(sliderValue);
    }, SLIDER_DELAY_MS);
    return () => clearTimeout(timer);
  }, [sliderValue, chapter, goToChapter]);

  const setFontScale = useCallback(
    (direction: 1 | -1) => {
      const next = stepFontScale(fontScale, direction);
      if (next === fontScale) return;
      if (!vertical) setLoading(true); // the src changes: the same position is restored after
      void update({ book_font_scale: next });
    },
    [fontScale, update, vertical],
  );

  const setBookTheme = useCallback(
    (next: BookTheme) => {
      if (next === theme) return;
      if (!vertical) setLoading(true);
      void update({ book_theme: next });
    },
    [theme, update, vertical],
  );

  const retry = useCallback(() => {
    setLoadFailedFrame(false);
    setLoading(true);
    setReloadNonce((value) => value + 1);
  }, []);

  return {
    item,
    book,
    nav,
    count,
    chapter,
    chapterTitle: book.chapters.find((entry) => entry.index === chapter)?.title ?? '',
    percent: bookPercent(chapter, bp, count),
    // Continuous mode scrolls into the next chapter by itself: only the end of the book shows.
    atEnd:
      bp >= Math.min(END_BP, BP_MAX) &&
      !loading &&
      !loadFailedFrame &&
      (!vertical || chapter >= count - 1),
    isLastChapter: chapter >= count - 1,
    vertical,
    strip,
    chapterUrl: (index: number) => bookChapterUrl(item.id, index, theme, fontScale),
    src,
    frameKey: `${chapter}:${reloadNonce}`,
    loading,
    frameFailed: loadFailedFrame,
    controlsVisible,
    keepControlsAlive: controls.keepAlive,
    panel,
    sliderValue: sliderValue ?? chapter,
    fontScale,
    theme,
    saveStatus: saver.status,
    prefsSaveFailed: saveFailed,
    prefsLoadFailed: loadFailed,
    onFrameLoad: frame.onLoad,
    goToChapter,
    step,
    toggleControls,
    openPanel,
    closePanel,
    setSliderValue,
    setFontScale,
    setBookTheme,
    retry,
  };
}

export type EpubReaderState = ReturnType<typeof useEpubReader>;
