import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { bookChapterUrl, type BookInfo, type Item } from '../../../../shared/items';
import { usePreferences, type BookTheme } from '../../../../shared/preferences';
import type { ReaderNav } from '../../../../shared/series';
import { useReaderProgress } from '../../hooks/useReaderProgress';
import type { ReaderShellProps } from '../../shell/ReaderShell';
import { SLIDER_DELAY_MS, useReaderChrome, useUnitSlider } from '../../shell/useReaderChrome';
import type { ReaderSource, UnitPosition } from '../../sources';
import { scrollFraction, useReaderInput, type ReaderIntent } from '../../input';
import { BP_MAX, stepFontScale } from '../locator';
import { useEpubFrame } from './useEpubFrame';
import { useEpubStrip, type StripJump } from './useEpubStrip';

interface Params {
  frameRef: RefObject<HTMLIFrameElement | null>;
  item: Item;
  book: BookInfo | null;
  nav: ReaderNav;
  source: ReaderSource;
  savedLocator: number | null;
  savedPosition: UnitPosition;
}

/** From here on the chapter counts as "read to the end" (offers the next chapter). */
const END_BP = 9900;

/** All behaviour of the EPUB reader: chapter, position, preferences, keys and the frame/strip. */
export function useEpubReader({
  frameRef,
  item,
  book,
  nav,
  source,
  savedLocator,
  savedPosition,
}: Params) {
  const count = source.unitCount;
  const { preferences, update } = usePreferences();
  const chrome = useReaderChrome();
  const { reportPosition, saveStatus } = useReaderProgress(
    item.id,
    source,
    savedLocator,
    savedPosition,
  );

  const [initial] = useState(() => ({ chapter: savedPosition.unit, bp: savedPosition.bp }));
  const [chapter, setChapter] = useState(initial.chapter);
  const [bp, setBp] = useState(initial.bp);
  // "Vertical" reading direction = continuous scroll through the chapters (same preference as the
  // manga strip). The page remounts the reader when it changes.
  const vertical = chrome.mode === 'vertical';
  const [loading, setLoading] = useState(!vertical); // the strip loads per chapter
  const [loadFailedFrame, setLoadFailedFrame] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
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

  const { closePanel, setPending, toggle: toggleControls } = chrome;

  const goToChapter = useCallback(
    (target: number, anchor: string | null = null) => {
      const next = source.clampUnit(target);
      closePanel();
      setPending(null);
      if (vertical) {
        // Continuous mode: scroll the strip to the chapter (anchors are not used here).
        positionRef.current = 0;
        shownRef.current = { chapter: next, bp: 0 };
        setBp(0);
        setChapter(next);
        setJump((value) => ({ chapter: next, bp: 0, nonce: value.nonce + 1 }));
        reportPosition(next, 0);
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
      reportPosition(next, 0); // the user moved: save the new position
    },
    [source, chapter, reportPosition, vertical, closePanel, setPending],
  );

  const step = useCallback(
    (direction: 'prev' | 'next') => {
      const target = chapter + (direction === 'next' ? 1 : -1);
      if (target >= 0 && target < count) goToChapter(target);
    },
    [goToChapter, chapter, count],
  );

  const onIntent = useCallback(
    (intent: ReaderIntent) => {
      switch (intent.type) {
        case 'prev':
        case 'next':
          step(intent.type);
          break;
        case 'first':
          goToChapter(0);
          break;
        case 'last':
          goToChapter(count - 1);
          break;
        case 'scrollPage':
        case 'scrollLine':
          scrollApi.current?.by(scrollFraction(intent));
          break;
        case 'scrollEdge':
          scrollApi.current?.edge(intent.sign < 0 ? 'top' : 'bottom');
          break;
        case 'toggleChrome':
          toggleControls();
          break;
      }
    },
    [step, goToChapter, count, toggleControls],
  );
  const { input, handleKey } = useReaderInput({
    source,
    mode: chrome.mode,
    handleChromeKey: chrome.handleKey,
    onIntent,
  });

  const frame = useEpubFrame({
    input,
    frameRef,
    chapter,
    positionRef,
    anchorRef,
    callbacks: {
      onPosition: (loadedChapter, value, shouldReport) => {
        if (loadedChapter !== chapter) return; // late event of a document we left
        setBp(value);
        if (shouldReport) reportPosition(loadedChapter, value);
      },
      onGoto: goToChapter,
      onIntent,
      onKey: handleKey,
      onLoaded: (ok) => {
        setLoading(false);
        setLoadFailedFrame(!ok);
      },
    },
  });

  const strip = useEpubStrip({
    input,
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
        if (shouldReport) reportPosition(stripChapter, value);
      },
      onGoto: goToChapter,
      onIntent,
      onKey: handleKey,
    },
  });

  const scrollBy = vertical ? strip.scrollBy : frame.scrollBy;
  const scrollToEdge = vertical ? strip.scrollToEdge : frame.scrollToEdge;
  useEffect(() => {
    scrollApi.current = { by: scrollBy, edge: scrollToEdge };
  }, [scrollBy, scrollToEdge]);

  // Slider: shows the value while dragging, opens the chapter once the user pauses.
  const slider = useUnitSlider({
    chrome,
    current: chapter,
    commit: goToChapter,
    delayMs: SLIDER_DELAY_MS,
  });

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

  const title = book?.title || item.title;
  // Continuous mode scrolls into the next chapter by itself: only the end of the book shows.
  const atEnd =
    bp >= Math.min(END_BP, BP_MAX) &&
    !loading &&
    !loadFailedFrame &&
    (!vertical || chapter >= count - 1);

  const shell: ReaderShellProps = {
    title,
    source,
    nav,
    unit: chapter,
    percent: source.codec.percent(chapter, bp, count),
    atEnd,
    mode: chrome.mode,
    saveStatus,
    chrome,
    slider,
    onStep: step,
    onGoTo: goToChapter,
    onModeChange: chrome.changeMode,
    zoom: null,
    text: { fontScale, theme, setFontScale, setTheme: setBookTheme },
  };

  return {
    item,
    title,
    count,
    chapter,
    vertical,
    strip,
    chapterUrl: (index: number) => bookChapterUrl(item.id, index, theme, fontScale),
    src,
    frameKey: `${chapter}:${reloadNonce}`,
    loading,
    frameFailed: loadFailedFrame,
    onFrameLoad: frame.onLoad,
    retry,
    position: { unit: chapter, bp },
    shell,
  };
}

export type EpubReaderState = ReturnType<typeof useEpubReader>;
