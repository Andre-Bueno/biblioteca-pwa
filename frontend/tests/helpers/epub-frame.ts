import { act, fireEvent } from '@testing-library/react';

export interface FakeChapter {
  doc: Document;
  win: Window;
  /** Current scrollTop of the fake document. */
  top: () => number;
  /** Moves the scroll like the user would (fires `scroll` in the iframe window). */
  scrollTo: (value: number) => void;
  /** Same as scrollTo but marks a wheel gesture first (a real user move). */
  userScrollTo: (value: number) => void;
  setScrollHeight: (value: number) => void;
}

interface Options {
  html?: string;
  scrollHeight?: number;
  clientHeight?: number;
  contentType?: string;
  /** Do not fire `load` (the test does it later). */
  skipLoad?: boolean;
}

/**
 * jsdom has no layout and does not fetch the iframe src: this fills the iframe document with a
 * fake chapter (geometry included), then fires `load` like the browser would.
 */
export function mountChapter(iframe: HTMLIFrameElement, options: Options = {}): FakeChapter {
  const doc = iframe.contentDocument!;
  const win = iframe.contentWindow!;
  if (!doc.documentElement) doc.appendChild(doc.createElement('html'));
  if (!doc.body) doc.documentElement.appendChild(doc.createElement('body'));
  doc.body.innerHTML = options.html ?? '<p>Texto do capitulo</p>';
  let scrollTop = 0;
  let scrollHeight = options.scrollHeight ?? 10000;
  const root = doc.documentElement;
  Object.defineProperty(root, 'scrollTop', {
    configurable: true,
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = Math.max(0, Math.min(value, scrollHeight - (options.clientHeight ?? 1000)));
    },
  });
  Object.defineProperty(root, 'scrollHeight', { configurable: true, get: () => scrollHeight });
  Object.defineProperty(root, 'clientHeight', {
    configurable: true,
    get: () => options.clientHeight ?? 1000,
  });
  Object.defineProperty(doc, 'scrollingElement', { configurable: true, get: () => root });
  Object.defineProperty(doc, 'contentType', {
    configurable: true,
    get: () => options.contentType ?? 'text/html',
  });
  Object.defineProperty(win, 'innerWidth', { configurable: true, value: 1000 });

  const chapter: FakeChapter = {
    doc,
    win,
    top: () => scrollTop,
    scrollTo(value) {
      scrollTop = value;
      act(() => {
        win.dispatchEvent(new Event('scroll'));
      });
    },
    userScrollTo(value) {
      act(() => {
        doc.dispatchEvent(new Event('wheel', { bubbles: true }));
      });
      chapter.scrollTo(value);
    },
    setScrollHeight(value) {
      scrollHeight = value;
    },
  };
  if (!options.skipLoad) fireEvent.load(iframe);
  return chapter;
}

export function clickIn(target: Element, clientX = 500): MouseEvent {
  const event = new MouseEvent('click', { bubbles: true, cancelable: true, clientX });
  act(() => {
    target.dispatchEvent(event);
  });
  return event;
}

export function keyIn(doc: Document, key: string): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  act(() => {
    doc.body.dispatchEvent(event);
  });
  return event;
}
