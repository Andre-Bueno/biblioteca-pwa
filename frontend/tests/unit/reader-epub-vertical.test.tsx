import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
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

const COUNT = 167; // like the manga EPUB: one page-image per spine item
const BOOK = {
  title: 'Manga em EPUB',
  authors: [],
  language: 'ja',
  chapters: Array.from({ length: COUNT }, (_, index) => ({ index, title: `PÃ¡gina ${index + 1}` })),
  toc: [{ title: 'Pagina 100', index: 99, anchor: null }],
  has_cover: false,
};
const PREFS = {
  theme: 'system',
  reading_direction: 'vertical',
  book_font_scale: 100,
  book_theme: 'auto',
};
const progressPuts = () => fakeApi.callsTo('PUT', '/api/v1/progress/bk-1');

const PAGE_HEIGHT = 1000;

// jsdom has no layout: the chapter wrappers are as tall as the style says and stack in order.
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

function setup(locator: number | null) {
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
  fakeApi.on('GET', '/api/v1/me/preferences', PREFS);
  renderApp('/ler/bk-1');
}

function chaptersMounted(): number[] {
  return screen
    .getAllByTestId('strip-chapter')
    .filter((node) => node.dataset.mounted === 'true')
    .map((node) => Number(node.dataset.chapter));
}

const topOf = (strip: HTMLElement, index: number) =>
  (strip.children[index] as HTMLElement).offsetTop;

/** Scroll position of the strip container (a plain number, like a real element would hold). */
function useScrollTop(container: HTMLElement) {
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

describe('EPUB reader: continuous vertical mode', () => {
  let restore: () => void;
  beforeEach(() => {
    fakeApi.reset();
    restore = fakeLayout();
  });
  afterEach(() => restore());

  it('renders a strip instead of the single frame, with only a window of chapters mounted', async () => {
    setup(50 * 10000 + 2500);
    const strip = await screen.findByTestId('epub-strip');
    expect(screen.queryByTestId('epub-frame')).toBeNull();
    expect(within(strip).getAllByTestId('strip-chapter')).toHaveLength(COUNT);
    expect(chaptersMounted()).toEqual([49, 50, 51, 52, 53]); // never the 167 at once
    for (const frame of screen.getAllByTestId('strip-frame')) {
      expect(frame).toHaveAttribute('sandbox', 'allow-same-origin');
    }
    expect(screen.getAllByTestId('strip-frame')[1]).toHaveAttribute(
      'src',
      '/api/v1/items/bk-1/book/chapters/50?theme=auto&size=100',
    );
  });

  it('never flashes the single-frame reader while the preference is still loading', async () => {
    signedIn();
    fakeApi.on('GET', '/api/v1/items/bk-1', makeItem({ id: 'bk-1', type: 'book', format: 'epub' }));
    fakeApi.on('GET', '/api/v1/items/bk-1/book', BOOK);
    fakeApi.on('GET', '/api/v1/progress/bk-1', () => {
      throw new ApiError(404, 'none');
    });
    fakeApi.on('PUT', '/api/v1/progress/bk-1', ({ body }: { body: unknown }) => ({
      ...(body as object),
    }));
    fakeApi.on('GET', '/api/v1/me/preferences', async () => {
      await new Promise((resolve) => setTimeout(resolve, 150)); // arrives after item and book
      return PREFS;
    });
    renderApp('/ler/bk-1');
    expect(screen.queryByTestId('epub-frame')).toBeNull();
    expect(await screen.findByTestId('epub-strip')).toBeInTheDocument();
    expect(screen.queryByTestId('epub-frame')).toBeNull();
  });

  it('lets a chapter that ships html/body height 100% shrink to its content (strip frames)', async () => {
    setup(0);
    await screen.findByTestId('epub-strip');
    const frame = screen.getAllByTestId('strip-frame')[0] as HTMLIFrameElement;
    const chapter = mountChapter(frame, { scrollHeight: PAGE_HEIGHT });
    for (const element of [chapter.doc.documentElement, chapter.doc.body]) {
      expect(element.style.getPropertyValue('height')).toBe('auto');
      expect(element.style.getPropertyPriority('height')).toBe('important');
      expect(element.style.getPropertyValue('min-height')).toMatch(/^0(px)?$/);
    }
  });

  it('keeps the single-frame reader for the other reading directions', async () => {
    signedIn();
    setup(null);
    fakeApi.on('GET', '/api/v1/me/preferences', { ...PREFS, reading_direction: 'rtl' });
    expect(await screen.findByTestId('epub-frame')).toBeInTheDocument();
    expect(screen.queryByTestId('epub-strip')).toBeNull();
  });

  it('moves the window and saves chapter*10000+offset while the user scrolls', async () => {
    setup(10 * 10000);
    const strip = await screen.findByTestId('epub-strip');
    const scrollTo = useScrollTop(strip);
    // Each mounted frame reports a page-sized document.
    for (const frame of screen.getAllByTestId('strip-frame') as HTMLIFrameElement[]) {
      mountChapter(frame, { scrollHeight: PAGE_HEIGHT, clientHeight: 800 });
    }
    await waitFor(() => expect(strip.children[10]).toHaveStyle({ height: `${PAGE_HEIGHT}px` }));

    await new Promise((resolve) => setTimeout(resolve, 450)); // past the post-jump settle window
    scrollTo(topOf(strip, 12) + 250);
    await waitFor(() => expect(chaptersMounted()).toEqual([11, 12, 13, 14, 15]));
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 122500 }));
    expect(screen.getByTestId('chapter-indicator')).toHaveTextContent(/13 de 167/);
  });

  it('does not save a lower position by itself (settling), only after a user gesture', async () => {
    setup(10 * 10000 + 5000);
    const strip = await screen.findByTestId('epub-strip');
    const scrollTo = useScrollTop(strip);
    for (const frame of screen.getAllByTestId('strip-frame') as HTMLIFrameElement[]) {
      mountChapter(frame, { scrollHeight: PAGE_HEIGHT, clientHeight: 800 });
    }
    await waitFor(() => expect(strip.children[10]).toHaveStyle({ height: `${PAGE_HEIGHT}px` }));
    await new Promise((resolve) => setTimeout(resolve, 450)); // past the post-jump settle window

    scrollTo(topOf(strip, 9), false); // layout shift: no wheel / touch
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(
      progressPuts().some((call) => (call.body as { locator: number }).locator === 90000),
    ).toBe(false);

    scrollTo(topOf(strip, 9)); // the user scrolled back: now it counts
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 90000 }));
  });

  it('jumps through the table of contents and saves the new chapter', async () => {
    setup(null);
    const strip = await screen.findByTestId('epub-strip');
    useScrollTop(strip);
    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    await user.click(screen.getByTestId('open-toc'));
    await user.click(await screen.findByText('Pagina 100'));
    await waitFor(() => expect(chaptersMounted()).toEqual([98, 99, 100, 101, 102]));
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 990000 }));
  });

  it('a jump resets the gesture: a scroll without gesture before the target loads saves nothing', async () => {
    setup(5 * 10000);
    const strip = await screen.findByTestId('epub-strip');
    const scrollTo = useScrollTop(strip);
    for (const frame of screen.getAllByTestId('strip-frame') as HTMLIFrameElement[]) {
      mountChapter(frame, { scrollHeight: PAGE_HEIGHT, clientHeight: 800 });
    }
    await waitFor(() => expect(strip.children[5]).toHaveStyle({ height: `${PAGE_HEIGHT}px` }));
    await new Promise((resolve) => setTimeout(resolve, 450));
    scrollTo(topOf(strip, 6)); // with a gesture: saved
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 60000 }));

    const { default: userEvent } = await import('@testing-library/user-event');
    const user = userEvent.setup();
    await user.click(screen.getByTestId('open-toc'));
    await user.click(await screen.findByText('Pagina 100'));
    await waitFor(() => expect(chaptersMounted()).toEqual([98, 99, 100, 101, 102]));
    await new Promise((resolve) => setTimeout(resolve, 450)); // past the post-jump suppression

    scrollTo(topOf(strip, 3), false); // layout noise; the target (99) has not loaded
    await new Promise((resolve) => setTimeout(resolve, 600));
    const locators = progressPuts().map((call) => (call.body as { locator: number }).locator);
    expect(locators.some((locator) => locator >= 30000 && locator < 40000)).toBe(false);
    expect(locators.at(-1)).toBe(990000);
  });

  it('at the bottom of the last chapter the progress is the end and the end card shows', async () => {
    setup(166 * 10000);
    const strip = await screen.findByTestId('epub-strip');
    const scrollTo = useScrollTop(strip);
    const total = () => topOf(strip, 166) + (strip.children[166] as HTMLElement).offsetHeight;
    Object.defineProperty(strip, 'scrollHeight', { configurable: true, get: total });
    Object.defineProperty(strip, 'clientHeight', { configurable: true, value: 800 });
    for (const frame of screen.getAllByTestId('strip-frame') as HTMLIFrameElement[]) {
      mountChapter(frame, { scrollHeight: PAGE_HEIGHT, clientHeight: 800 });
    }
    await waitFor(() => expect(strip.children[166]).toHaveStyle({ height: `${PAGE_HEIGHT}px` }));
    await new Promise((resolve) => setTimeout(resolve, 450));

    scrollTo(total() - 800);
    expect(await screen.findByTestId('book-finished')).toBeInTheDocument();
    await waitFor(() => expect(progressPuts().at(-1)?.body).toMatchObject({ locator: 1669999 }));
  });

  it('on a touch device the reader opens in full screen; tap and the reveal button bring the bars back', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query.includes('pointer: coarse'),
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      })),
    );
    try {
      setup(0);
      const strip = await screen.findByTestId('epub-strip');
      useScrollTop(strip);
      expect(screen.queryByTestId('reader-controls')).toBeNull();
      expect(screen.getByTestId('epub-pill')).toHaveTextContent('1/167');
      const chapter = mountChapter(screen.getAllByTestId('strip-frame')[0] as HTMLIFrameElement, {
        html: '<p>Texto</p>',
        scrollHeight: PAGE_HEIGHT,
      });
      clickIn(chapter.doc.querySelector('p')!, 500);
      expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
      expect(screen.queryByTestId('epub-pill')).toBeNull();
      clickIn(chapter.doc.querySelector('p')!, 500);
      const { default: userEvent } = await import('@testing-library/user-event');
      await userEvent.setup().click(screen.getByTestId('show-controls'));
      expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('a tap in the middle of a chapter toggles the controls; internal links jump chapters', async () => {
    setup(0);
    const strip = await screen.findByTestId('epub-strip');
    useScrollTop(strip);
    const frames = screen.getAllByTestId('strip-frame') as HTMLIFrameElement[];
    const chapter = mountChapter(frames[0]!, {
      html: '<p>Texto</p><a href="?goto=2#x">ir</a>',
      scrollHeight: PAGE_HEIGHT,
    });
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    clickIn(chapter.doc.querySelector('p')!, 500);
    expect(screen.queryByTestId('reader-controls')).toBeNull();
    const event = clickIn(chapter.doc.querySelector('a')!);
    expect(event.defaultPrevented).toBe(true);
    await waitFor(() => expect(chaptersMounted()).toEqual([1, 2, 3, 4, 5]));
  });
});
