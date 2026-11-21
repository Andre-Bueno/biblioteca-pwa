// reg_001 (issue #7): zooming the EPUB reader (pinch on iOS, ctrl+wheel / ctrl+"+" on desktop)
// must not change chapter, move the reading position or save a new progress. Covers both modes:
// continuous vertical strip and single chapter.
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../src/shared/api-client/errors';
import { clickIn, mountChapter } from '../helpers/epub-frame';
import { fakeApi, makeItem, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const COUNT = 167;
const BOOK = {
  title: 'Manga em EPUB',
  authors: [],
  language: 'ja',
  chapters: Array.from({ length: COUNT }, (_, index) => ({ index, title: `Pagina ${index + 1}` })),
  toc: [],
  has_cover: false,
};
const PAGE_HEIGHT = 1000;
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const progressPuts = () => fakeApi.callsTo('PUT', '/api/v1/progress/bk-1');
const locators = () => progressPuts().map((call) => (call.body as { locator: number }).locator);

function setup(locator: number | null, direction: 'vertical' | 'rtl') {
  signedIn();
  fakeApi.on(
    'GET',
    '/api/v1/items/bk-1',
    makeItem({ id: 'bk-1', type: 'book', title: 'Manga', format: 'epub', page_count: null }),
  );
  fakeApi.on('GET', '/api/v1/items/bk-1/book', BOOK);
  fakeApi.on('GET', '/api/v1/progress/bk-1', () => {
    if (locator === null) throw new ApiError(404, 'none');
    return { item_id: 'bk-1', locator, percent: 1, finished: false, updated_at: 'x' };
  });
  fakeApi.on('PUT', '/api/v1/progress/bk-1', ({ body }: { body: unknown }) => ({
    ...(body as object),
  }));
  fakeApi.on('GET', '/api/v1/me/preferences', {
    theme: 'system',
    reading_direction: direction,
    book_font_scale: 100,
    book_theme: 'auto',
  });
  renderApp('/ler/bk-1');
}

/** Dispatches a touch event carrying `count` fingers (jsdom has no Touch support). */
function touches(target: EventTarget, type: string, count: number, x = 300) {
  const event = new Event(type, { bubbles: true }) as Event & {
    touches: unknown[];
    changedTouches: unknown[];
  };
  event.touches = Array.from({ length: count }, (_, i) => ({ clientX: x + i * 80, clientY: 200 }));
  event.changedTouches = [{ clientX: x, clientY: 205 }];
  act(() => {
    target.dispatchEvent(event);
  });
}

// ---------------------------------------------------------------------------------------------
// Continuous vertical strip
// ---------------------------------------------------------------------------------------------

function fakeLayout() {
  const proto = HTMLElement.prototype;
  const height = Object.getOwnPropertyDescriptor(proto, 'offsetHeight');
  const top = Object.getOwnPropertyDescriptor(proto, 'offsetTop');
  Object.defineProperty(proto, 'offsetHeight', {
    configurable: true,
    get(this: HTMLElement) {
      return 'chapter' in this.dataset ? Number.parseFloat(this.style.height) || 0 : 0;
    },
  });
  Object.defineProperty(proto, 'offsetTop', {
    configurable: true,
    get(this: HTMLElement) {
      if (!('chapter' in this.dataset)) return 0;
      let sum = 0;
      for (let node = this.previousElementSibling; node; node = node.previousElementSibling) {
        sum += Number.parseFloat((node as HTMLElement).style.height) || 0;
      }
      return sum;
    },
  });
  return () => {
    if (height) Object.defineProperty(proto, 'offsetHeight', height);
    if (top) Object.defineProperty(proto, 'offsetTop', top);
  };
}

const topOf = (strip: HTMLElement, index: number) =>
  (strip.children[index] as HTMLElement).offsetTop;

function makeScrollTop(container: HTMLElement) {
  let value = 0;
  Object.defineProperty(container, 'scrollTop', {
    configurable: true,
    get: () => value,
    set: (next: number) => {
      value = next;
    },
  });
  return (next: number, gesture = true) => {
    if (gesture) fireEvent.wheel(container);
    value = next;
    act(() => {
      container.dispatchEvent(new Event('scroll'));
    });
  };
}

async function openStrip(locator: number) {
  setup(locator, 'vertical');
  const strip = await screen.findByTestId('epub-strip');
  const scrollTo = makeScrollTop(strip);
  const frames = screen.getAllByTestId('strip-frame') as HTMLIFrameElement[];
  const chapters = frames.map((frame) =>
    mountChapter(frame, { scrollHeight: PAGE_HEIGHT, clientHeight: 800 }),
  );
  await waitFor(() => expect(strip.children[10]).toHaveStyle({ height: `${PAGE_HEIGHT}px` }));
  await wait(450); // past the post-jump settle window
  return { strip, scrollTo, frames, chapters };
}

describe('reg_001 epub zoom: continuous strip', { timeout: 20000 }, () => {
  let restoreLayout: () => void;
  const width = window.innerWidth;
  beforeEach(() => {
    fakeApi.reset();
    restoreLayout = fakeLayout();
  });
  afterEach(() => {
    restoreLayout();
    window.innerWidth = width;
  });

  it('a pinch is not a user scroll: the scroll noise it causes below the opening point is never saved', async () => {
    const { strip, scrollTo } = await openStrip(10 * 10000);
    touches(strip, 'touchstart', 2);
    touches(strip, 'touchmove', 2);
    scrollTo(topOf(strip, 9), false); // the browser scrolled while zooming
    touches(strip, 'touchend', 0);
    await wait(1400);
    expect(locators().some((locator) => locator < 100000)).toBe(false);
  });

  it('a scroll discarded during the pinch is looked at again afterwards (last point is not lost)', async () => {
    const { strip, scrollTo } = await openStrip(10 * 10000);
    touches(strip, 'touchstart', 2);
    touches(strip, 'touchmove', 2);
    scrollTo(topOf(strip, 12), false);
    touches(strip, 'touchend', 0);
    await waitFor(() => expect(locators()).toContain(120000), { timeout: 4000 });
  });

  it('a pinch (real touchstart with two fingers) is never a centre tap, and taps work 700 ms later', async () => {
    setup(0, 'vertical');
    const strip = await screen.findByTestId('epub-strip');
    makeScrollTop(strip);
    const chapter = mountChapter(screen.getAllByTestId('strip-frame')[0] as HTMLIFrameElement, {
      html: '<p>Texto</p>',
      scrollHeight: PAGE_HEIGHT,
    });
    const target = chapter.doc.querySelector('p')!;
    touches(target, 'touchstart', 2);
    touches(target, 'touchend', 0);
    clickIn(target, 500); // synthetic click at the end of the pinch
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    await wait(700);
    clickIn(target, 500);
    expect(screen.queryByTestId('reader-controls')).toBeNull(); // a normal tap toggles again
  });

  it('a normal scroll with a gesture saves again 700 ms after a pinch', async () => {
    const { strip, scrollTo } = await openStrip(10 * 10000);
    touches(strip, 'touchstart', 2);
    touches(strip, 'touchmove', 2);
    touches(strip, 'touchend', 0);
    await wait(700);
    scrollTo(topOf(strip, 9)); // wheel = user gesture, lower than where it opened
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 90000 }));
  });

  it('a lost touchend does not lock saving: a one-finger touchstart ends the pinch', async () => {
    const { strip, scrollTo } = await openStrip(10 * 10000);
    touches(strip, 'touchstart', 2);
    touches(strip, 'touchmove', 2); // ... and the touchend never arrives
    touches(strip, 'touchstart', 1);
    scrollTo(topOf(strip, 12), false);
    await waitFor(() => expect(locators()).toContain(120000), { timeout: 4000 });
  });

  it('ctrl + wheel (browser zoom) is not a user gesture', async () => {
    const { strip, scrollTo } = await openStrip(10 * 10000);
    fireEvent.wheel(strip, { ctrlKey: true });
    scrollTo(topOf(strip, 9), false);
    await wait(1200);
    expect(locators().some((locator) => locator < 100000)).toBe(false);
  });

  it('a width change keeps chapter and relative offset while heights reflow, saving nothing', async () => {
    const { strip, scrollTo, frames, chapters } = await openStrip(10 * 10000);
    scrollTo(topOf(strip, 12) + 250);
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 122500 }));
    const saved = progressPuts().length;

    window.innerWidth = width / 2;
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    chapters[3]!.setScrollHeight(2 * PAGE_HEIGHT); // chapter 12 reflows to twice the height
    fireEvent.load(frames[3]!);
    await waitFor(() => expect(strip.children[12]).toHaveStyle({ height: `${2 * PAGE_HEIGHT}px` }));
    expect(strip.scrollTop).toBe(topOf(strip, 12) + 500); // still 25% into chapter 12
    scrollTo(topOf(strip, 11), false); // reflow noise inside the hold window
    await wait(1200);
    expect(progressPuts()).toHaveLength(saved);
  });

  it('a height-only resize (Safari toolbars) neither holds nor re-applies the position', async () => {
    const { strip, scrollTo, frames, chapters } = await openStrip(10 * 10000);
    scrollTo(topOf(strip, 12) + 250);
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 122500 }));
    act(() => {
      window.dispatchEvent(new Event('resize')); // same width
    });
    chapters[3]!.setScrollHeight(2 * PAGE_HEIGHT);
    fireEvent.load(frames[3]!);
    await waitFor(() => expect(strip.children[12]).toHaveStyle({ height: `${2 * PAGE_HEIGHT}px` }));
    expect(strip.scrollTop).toBe(topOf(strip, 12) + 250); // untouched
  });

  it('a resize right after the user scrolled does not pull the scroll back', async () => {
    const { strip, scrollTo, frames, chapters } = await openStrip(10 * 10000);
    scrollTo(topOf(strip, 12) + 250); // wheel just now
    window.innerWidth = width / 2;
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    chapters[3]!.setScrollHeight(2 * PAGE_HEIGHT);
    fireEvent.load(frames[3]!);
    await waitFor(() => expect(strip.children[12]).toHaveStyle({ height: `${2 * PAGE_HEIGHT}px` }));
    expect(strip.scrollTop).toBe(topOf(strip, 12) + 250);
  });

  it('a user scroll during the hold ends it and is saved', async () => {
    const { strip, scrollTo, frames, chapters } = await openStrip(10 * 10000);
    scrollTo(topOf(strip, 12) + 250);
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 122500 }));
    window.innerWidth = width / 2;
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    await wait(200);
    scrollTo(topOf(strip, 13) + 100); // the user moves on during the hold window
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 131000 }));
    const before = strip.scrollTop;
    chapters[3]!.setScrollHeight(2 * PAGE_HEIGHT);
    fireEvent.load(frames[3]!);
    await waitFor(() => expect(strip.children[12]).toHaveStyle({ height: `${2 * PAGE_HEIGHT}px` }));
    expect(strip.scrollTop).not.toBe(topOf(strip, 12) + 500); // not yanked back to the old anchor
    expect(strip.scrollTop).toBeGreaterThanOrEqual(before);
  });
});

// ---------------------------------------------------------------------------------------------
// Single chapter
// ---------------------------------------------------------------------------------------------

describe('reg_001 epub zoom: single chapter', { timeout: 20000 }, () => {
  beforeEach(() => fakeApi.reset());

  async function openChapter() {
    setup(1 * 10000 + 5000, 'rtl');
    const chapter = mountChapter((await screen.findByTestId('epub-frame')) as HTMLIFrameElement);
    await waitFor(() => expect(chapter.top()).toBeGreaterThan(0));
    await wait(50);
    return chapter;
  }
  const frameSrc = () => screen.getByTestId('epub-frame').getAttribute('src');
  const widen = (chapter: { win: Window }, value: number) => {
    Object.defineProperty(chapter.win, 'innerWidth', { configurable: true, value });
    act(() => {
      chapter.win.dispatchEvent(new Event('resize'));
    });
  };

  it('a pinch (touchstart with 2 fingers, fingers apart on release) is not a chapter swipe or tap', async () => {
    const chapter = await openChapter();
    const src = frameSrc();
    touches(chapter.doc.body, 'touchstart', 1, 300);
    touches(chapter.doc.body, 'touchstart', 2, 300);
    touches(chapter.doc.body, 'touchmove', 2, 300);
    touches(chapter.doc.body, 'touchend', 1, 100);
    touches(chapter.doc.body, 'touchend', 0, 100);
    expect(frameSrc()).toBe(src);
    clickIn(chapter.doc.body, 500);
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
  });

  it('a pinch whose second touchstart never reaches the document is still not a swipe', async () => {
    const chapter = await openChapter();
    const src = frameSrc();
    touches(chapter.doc.body, 'touchstart', 1, 300);
    touches(chapter.doc.body, 'touchmove', 2, 300);
    touches(chapter.doc.body, 'touchend', 0, 100);
    expect(frameSrc()).toBe(src);
  });

  it('swipe, centre tap and scroll work again 700 ms after a pinch', async () => {
    const chapter = await openChapter();
    touches(chapter.doc.body, 'touchstart', 2);
    touches(chapter.doc.body, 'touchend', 0);
    await wait(700);
    clickIn(chapter.doc.body, 500);
    expect(screen.queryByTestId('reader-controls')).toBeNull();
    touches(chapter.doc.body, 'touchstart', 1, 300);
    touches(chapter.doc.body, 'touchend', 0, 100);
    expect(frameSrc()).toContain('/chapters/2?');
  });

  it('a width change re-applies the position and saves nothing below where it opened', async () => {
    const chapter = await openChapter();
    const before = chapter.top();
    touches(chapter.doc.body, 'touchstart', 2);
    chapter.scrollTo(before + 1000); // moved by the zoom (discarded)
    widen(chapter, 600);
    expect(Math.abs(chapter.top() - before)).toBeLessThan(10); // back where the reader was
    chapter.scrollTo(100); // reflow noise inside the hold window
    await wait(1400);
    expect(locators().some((locator) => locator < 15000)).toBe(false);
  });
  it('a height-only resize neither holds nor re-applies', async () => {
    const chapter = await openChapter();
    touches(chapter.doc.body, 'touchstart', 2);
    chapter.scrollTo(chapter.top() + 1000); // discarded (pinch)
    const moved = chapter.top();
    act(() => {
      chapter.win.dispatchEvent(new Event('resize')); // same width
    });
    expect(chapter.top()).toBe(moved);
  });

  it('a user scroll during the hold ends it and is saved', async () => {
    const chapter = await openChapter();
    widen(chapter, 600);
    await wait(200);
    chapter.userScrollTo(chapter.top() + 1000);
    await waitFor(() => expect(progressPuts().length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('a lost touchend does not lock saving; a discarded scroll is re-read afterwards', async () => {
    const chapter = await openChapter();
    touches(chapter.doc.body, 'touchstart', 2);
    touches(chapter.doc.body, 'touchmove', 2);
    touches(chapter.doc.body, 'touchstart', 1); // the touchend of the pinch was lost
    chapter.scrollTo(chapter.top() + 1500);
    await waitFor(() => expect(progressPuts().length).toBeGreaterThan(0), { timeout: 3000 });
  });

  it('a scroll discarded during the pinch is looked at again once it is over', async () => {
    const chapter = await openChapter();
    touches(chapter.doc.body, 'touchstart', 2);
    touches(chapter.doc.body, 'touchmove', 2);
    chapter.scrollTo(chapter.top() + 1500);
    expect(progressPuts()).toHaveLength(0);
    touches(chapter.doc.body, 'touchend', 0);
    await waitFor(() => expect(progressPuts().length).toBeGreaterThan(0), { timeout: 4000 });
  });

  it('ctrl + wheel (browser zoom) is not a user gesture', async () => {
    const chapter = await openChapter();
    act(() => {
      chapter.doc.dispatchEvent(new WheelEvent('wheel', { bubbles: true, ctrlKey: true }));
    });
    chapter.scrollTo(100); // far below where the chapter opened
    await wait(1200);
    expect(progressPuts()).toHaveLength(0);
  });
});
