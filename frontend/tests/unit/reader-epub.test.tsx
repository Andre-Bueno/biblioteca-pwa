import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../src/shared/api-client/errors';
import { clickIn, keyIn, mountChapter } from '../helpers/epub-frame';
import { apiError, fakeApi, makeItem, makeSeriesDetail, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const BOOK = {
  title: 'Livro Um <b>',
  authors: ['Autora Um'],
  language: 'pt-BR',
  chapters: [
    { index: 0, title: 'Capa' },
    { index: 1, title: 'Parte 1' },
    { index: 2, title: 'Parte 2' },
  ],
  toc: [
    { title: 'Capa', index: 0, anchor: null },
    { title: 'Parte 1', index: 1, anchor: 'p1' },
    { title: 'Parte 2', index: 2, anchor: null },
  ],
  has_cover: true,
};

const PREFS = {
  theme: 'system',
  reading_direction: 'rtl',
  book_font_scale: 100,
  book_theme: 'auto',
};
const progressPuts = () => fakeApi.callsTo('PUT', '/api/v1/progress/bk-1');
const prefPuts = () => fakeApi.callsTo('PUT', '/api/v1/me/preferences');
const chapterSrc = (n: number, theme = 'auto', size = 100) =>
  `/api/v1/items/bk-1/book/chapters/${n}?theme=${theme}&size=${size}`;

interface Options {
  locator?: number | null;
  prefs?: object | (() => unknown);
  book?: object | (() => unknown);
  progressPut?: (ctx: { body: unknown }) => unknown;
  series?: boolean;
  item?: Record<string, unknown>;
}

function setup(route = '/ler/bk-1', options: Options = {}) {
  signedIn();
  fakeApi.on(
    'GET',
    '/api/v1/items/bk-1',
    makeItem({
      id: 'bk-1',
      type: 'book',
      title: 'Livro Um',
      format: 'epub',
      page_count: null,
      ...options.item,
    }),
  );
  fakeApi.on('GET', '/api/v1/items/bk-1/book', options.book ?? BOOK);
  fakeApi.on('GET', '/api/v1/progress/bk-1', () => {
    if (options.locator == null) throw new ApiError(404, 'none');
    return {
      item_id: 'bk-1',
      locator: options.locator,
      percent: 10,
      finished: false,
      updated_at: 'x',
    };
  });
  fakeApi.on(
    'PUT',
    '/api/v1/progress/bk-1',
    options.progressPut ?? (({ body }: { body: unknown }) => ({ ...(body as object) })),
  );
  if (options.prefs) fakeApi.on('GET', '/api/v1/me/preferences', options.prefs);
  if (options.series) {
    fakeApi.on(
      'GET',
      '/api/v1/series/serie-1',
      makeSeriesDetail({
        chapters: [
          {
            id: 'bk-1',
            title: 'Livro Um',
            number: 1,
            page_count: null,
            type: 'book',
            progress: null,
          },
          {
            id: 'bk-2',
            title: 'Livro Dois',
            number: 2,
            page_count: null,
            type: 'book',
            progress: null,
          },
        ],
      }),
    );
  }
  renderApp(route);
}

async function openFrame() {
  return (await screen.findByTestId('epub-frame')) as HTMLIFrameElement;
}

describe('EPUB reader: choosing the reader and the iframe', () => {
  beforeEach(() => fakeApi.reset());

  it('a book opens the EPUB reader; a manga keeps opening the manga reader', async () => {
    setup();
    expect(await screen.findByTestId('epub-reader')).toBeInTheDocument();
    expect(screen.queryByTestId('reader')).not.toBeInTheDocument();
  });

  it('the manga reader is still used for manga items on the same route', async () => {
    signedIn();
    fakeApi.on('GET', '/api/v1/items/m-1', makeItem({ id: 'm-1', page_count: 4 }));
    fakeApi.on('GET', '/api/v1/progress/m-1', () => {
      throw new ApiError(404, 'none');
    });
    fakeApi.on('PUT', '/api/v1/progress/m-1', () => ({}));
    renderApp('/ler/m-1');
    expect(await screen.findByTestId('reader')).toBeInTheDocument();
    expect(screen.queryByTestId('epub-reader')).not.toBeInTheDocument();
    expect(fakeApi.callsTo('GET', '/api/v1/items/m-1')).toHaveLength(1);
  });

  it('renders the book in a sandboxed iframe with exactly allow-same-origin', async () => {
    setup();
    const frame = await openFrame();
    expect(frame.getAttribute('sandbox')).toBe('allow-same-origin');
    expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(frame).toHaveAttribute('src', chapterSrc(0));
    expect(frame.getAttribute('title')).toContain('Livro Um');
    expect(frame.getAttribute('title')).toContain('capítulo 1 de 3');
  });

  it('the sandbox never gains script/popup/form/navigation rights, whatever the state', async () => {
    setup('/ler/bk-1', {
      locator: 10000,
      prefs: { ...PREFS, book_theme: 'sepia', book_font_scale: 130 },
    });
    const frame = await openFrame();
    const check = () => {
      const sandbox = screen.getByTestId('epub-frame').getAttribute('sandbox') ?? '';
      for (const bad of ['allow-scripts', 'allow-popups', 'allow-forms', 'allow-top-navigation']) {
        expect(sandbox).not.toContain(bad);
      }
      expect(sandbox).toBe('allow-same-origin');
    };
    check();
    mountChapter(frame);
    await userEvent.setup().click(screen.getByTestId('chapter-next'));
    check();
    await userEvent.setup().click(screen.getByTestId('open-settings'));
    await userEvent.setup().click(screen.getByTestId('font-larger'));
    check();
    await userEvent.setup().click(screen.getByTestId('book-theme-dark'));
    check();
    expect(screen.getByTestId('epub-frame').getAttribute('src')).toBe(chapterSrc(2, 'dark', 140));
  });

  it('starts at the saved chapter with the saved theme and size', async () => {
    setup('/ler/bk-1', {
      locator: 2 * 10000 + 2500,
      prefs: { ...PREFS, book_theme: 'sepia', book_font_scale: 130 },
    });
    expect(await openFrame()).toHaveAttribute('src', chapterSrc(2, 'sepia', 130));
  });

  it('shows title and author as plain text (no HTML from the server in the app DOM)', async () => {
    setup();
    await openFrame();
    const title = screen.getByTestId('book-title');
    expect(title.textContent).toBe('Livro Um <b>');
    expect(title.querySelector('b')).toBeNull();
  });
});

describe('EPUB reader: states', () => {
  beforeEach(() => fakeApi.reset());

  it('shows a spinner while loading', async () => {
    signedIn();
    fakeApi.on('GET', '/api/v1/items/bk-1', () => new Promise(() => undefined));
    renderApp('/ler/bk-1');
    expect(await screen.findByTestId('reader-loading')).toBeInTheDocument();
  });

  it('item not found', async () => {
    signedIn();
    renderApp('/ler/bk-1');
    expect(await screen.findByTestId('reader-message')).toHaveTextContent('não encontrado');
  });

  it('book structure not found', async () => {
    setup('/ler/bk-1', {
      book: () => {
        throw new ApiError(404, 'x');
      },
    });
    expect(await screen.findByTestId('reader-message')).toHaveTextContent('Livro não encontrado');
  });

  it('error with retry', async () => {
    let attempts = 0;
    setup('/ler/bk-1', {
      book: () => {
        attempts += 1;
        if (attempts === 1) throw new ApiError(500, 'down');
        return BOOK;
      },
    });
    expect(await screen.findByTestId('reader-message')).toHaveTextContent('Não foi possível abrir');
    await userEvent.setup().click(screen.getByRole('button', { name: /tentar novamente/i }));
    expect(await openFrame()).toBeInTheDocument();
  });

  it('empty book (no chapters)', async () => {
    setup('/ler/bk-1', { book: { ...BOOK, chapters: [], toc: [] } });
    expect(await screen.findByTestId('reader-message')).toHaveTextContent('não tem capítulos');
  });

  it('malformed server data is ignored instead of crashing', async () => {
    setup('/ler/bk-1', {
      book: {
        title: 5,
        authors: 'x',
        chapters: [{ index: 'a' }, { index: 0, title: 'Um' }],
        toc: null,
      },
    });
    await openFrame();
    expect(screen.getByTestId('chapter-indicator')).toHaveTextContent('Capítulo 1 de 1');
  });

  it('shows the loading overlay until the chapter loads', async () => {
    setup();
    const frame = await openFrame();
    expect(screen.getByTestId('chapter-loading')).toBeInTheDocument();
    mountChapter(frame);
    await waitFor(() => expect(screen.queryByTestId('chapter-loading')).not.toBeInTheDocument());
  });

  it('a chapter that did not load as HTML shows an error and can be retried', async () => {
    setup();
    const frame = await openFrame();
    mountChapter(frame, { contentType: 'application/json' });
    expect(await screen.findByTestId('chapter-error')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByTestId('chapter-retry'));
    expect(screen.queryByTestId('chapter-error')).not.toBeInTheDocument();
    mountChapter(await openFrame());
    await waitFor(() => expect(screen.queryByTestId('chapter-loading')).not.toBeInTheDocument());
  });
});

describe('EPUB reader: table of contents and chapters', () => {
  beforeEach(() => fakeApi.reset());

  it('lists the TOC, marks the current entry and opens the chosen chapter', async () => {
    setup();
    mountChapter(await openFrame());
    const user = userEvent.setup();
    await user.click(screen.getByTestId('open-toc'));
    const items = screen.getAllByTestId('toc-item');
    expect(items.map((item) => item.textContent)).toEqual(['Capa', 'Parte 1', 'Parte 2']);
    expect(items[0]).toHaveAttribute('aria-current', 'true');
    await user.click(items[1]!);
    expect(screen.queryByTestId('toc')).not.toBeInTheDocument(); // closes after choosing
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(1));
    expect(screen.getByTestId('chapter-indicator')).toHaveTextContent('Capítulo 2 de 3');
  });

  it('a TOC entry with an anchor scrolls to it after the chapter loads', async () => {
    setup();
    mountChapter(await openFrame());
    const user = userEvent.setup();
    await user.click(screen.getByTestId('open-toc'));
    await user.click(screen.getAllByTestId('toc-item')[1]!);
    const chapter = mountChapter(screen.getByTestId('epub-frame') as HTMLIFrameElement, {
      html: '<h2 id="p1">Parte</h2>',
      skipLoad: true,
    });
    // like a real layout: the element moves up as the document scrolls
    chapter.doc.getElementById('p1')!.getBoundingClientRect = () =>
      ({ top: 700 - chapter.top() }) as DOMRect;
    fireEvent.load(screen.getByTestId('epub-frame'));
    expect(chapter.top()).toBe(700);
  });

  it('the TOC is a dialog: focus moves in, Esc closes it, focus returns to the button', async () => {
    setup();
    mountChapter(await openFrame());
    const user = userEvent.setup();
    const opener = screen.getByTestId('open-toc');
    await user.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Índice' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('falls back to the chapter list when the book has no TOC', async () => {
    setup('/ler/bk-1', { book: { ...BOOK, toc: [] } });
    mountChapter(await openFrame());
    await userEvent.setup().click(screen.getByTestId('open-toc'));
    expect(screen.getAllByTestId('toc-item')).toHaveLength(3);
  });

  it('previous / next buttons change the chapter and respect the limits', async () => {
    setup();
    mountChapter(await openFrame());
    const user = userEvent.setup();
    expect(screen.getByTestId('chapter-prev')).toBeDisabled();
    await user.click(screen.getByTestId('chapter-next'));
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(1));
    await user.click(screen.getByTestId('chapter-next'));
    expect(screen.getByTestId('chapter-next')).toBeDisabled();
    expect(screen.getByTestId('chapter-indicator')).toHaveTextContent('Capítulo 3 de 3 · 67%');
    await user.click(screen.getByTestId('chapter-prev'));
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(1));
  });

  it('the slider jumps to a chapter once the user pauses', async () => {
    setup();
    mountChapter(await openFrame());
    fireEvent.change(screen.getByTestId('chapter-slider'), { target: { value: '2' } });
    expect(screen.getByTestId('chapter-slider')).toHaveValue('2');
    await waitFor(() =>
      expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(2)),
    );
  });

  it('an internal link (?goto=) is intercepted and opens that chapter and anchor', async () => {
    setup();
    const chapter = mountChapter(await openFrame(), {
      html: '<a id="l" href="?goto=2#sec">ir</a><a id="x" href="https://exemplo.com/">fora</a>',
    });
    const link = chapter.doc.getElementById('l')!;
    const event = clickIn(link);
    expect(event.defaultPrevented).toBe(true);
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(2));
    // the anchor is applied on the next load
    const next = mountChapter(screen.getByTestId('epub-frame') as HTMLIFrameElement, {
      html: '<p id="sec">alvo</p>',
      skipLoad: true,
    });
    next.doc.getElementById('sec')!.getBoundingClientRect = () =>
      ({ top: 321 - next.top() }) as DOMRect;
    fireEvent.load(screen.getByTestId('epub-frame'));
    expect(next.top()).toBe(321);
  });

  it('any other link is blocked so the iframe never navigates away', async () => {
    setup();
    const chapter = mountChapter(await openFrame(), {
      html: '<a id="x" href="https://exemplo.com/">fora</a><a id="h" href="#nota">nota</a>',
    });
    expect(clickIn(chapter.doc.getElementById('x')!).defaultPrevented).toBe(true);
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(0));
    // in-chapter anchors keep working natively
    expect(clickIn(chapter.doc.getElementById('h')!).defaultPrevented).toBe(false);
  });

  it('a tap in the middle shows/hides the controls; a tap on the edge does not', async () => {
    setup();
    const chapter = mountChapter(await openFrame());
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    clickIn(chapter.doc.body, 20); // edge
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    clickIn(chapter.doc.body, 500);
    expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByTestId('show-controls'));
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
  });

  it('a clear horizontal swipe changes the chapter', async () => {
    setup();
    const chapter = mountChapter(await openFrame());
    const touch = (type: string, x: number, y: number) => {
      const event = new Event(type, { bubbles: true }) as Event & {
        touches: unknown[];
        changedTouches: unknown[];
      };
      const point = { clientX: x, clientY: y };
      event.touches = type === 'touchend' ? [] : [point];
      event.changedTouches = [point];
      act(() => {
        chapter.doc.body.dispatchEvent(event);
      });
    };
    touch('touchstart', 300, 200);
    touch('touchend', 100, 210);
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(1));
    // a mostly vertical move is only scrolling
    touch('touchstart', 300, 200);
    touch('touchend', 150, 500);
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(1));
  });
});

describe('EPUB reader: keyboard', () => {
  beforeEach(() => fakeApi.reset());

  it('arrows change chapter, PageUp/PageDown/Home/End scroll', async () => {
    setup();
    const chapter = mountChapter(await openFrame());
    const frameSrc = () => screen.getByTestId('epub-frame').getAttribute('src');
    fireEvent.keyDown(window, { key: 'PageDown' });
    expect(chapter.top()).toBe(900);
    fireEvent.keyDown(window, { key: 'PageUp' });
    expect(chapter.top()).toBe(0);
    fireEvent.keyDown(window, { key: 'End' });
    expect(chapter.top()).toBe(9000); // the end of the scrollable range
    fireEvent.keyDown(window, { key: 'Home' });
    expect(chapter.top()).toBe(0);
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(chapter.top()).toBe(100);
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(frameSrc()).toBe(chapterSrc(1));
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(frameSrc()).toBe(chapterSrc(0));
    fireEvent.keyDown(window, { key: 'ArrowLeft' }); // already first: nothing happens
    expect(frameSrc()).toBe(chapterSrc(0));
  });

  it('keys pressed inside the iframe document work too', async () => {
    setup();
    const chapter = mountChapter(await openFrame());
    expect(keyIn(chapter.doc, 'ArrowRight').defaultPrevented).toBe(true);
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(1));
  });

  it('keys do not act while the slider has the focus or a panel is open', async () => {
    setup();
    mountChapter(await openFrame());
    const slider = screen.getByTestId('chapter-slider');
    slider.focus();
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(0));
    await userEvent.setup().click(screen.getByTestId('open-toc'));
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(0));
  });

  it('"m" toggles the controls', async () => {
    setup();
    mountChapter(await openFrame());
    fireEvent.keyDown(window, { key: 'm' });
    expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'm' });
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
  });
});

describe('EPUB reader: restoring the position', () => {
  beforeEach(() => fakeApi.reset());

  it('scrolls the chapter to the saved offset', async () => {
    setup('/ler/bk-1', { locator: 10000 + 5000 });
    const frame = await openFrame();
    expect(frame).toHaveAttribute('src', chapterSrc(1));
    const chapter = mountChapter(frame); // range = 9000
    expect(chapter.top()).toBeCloseTo((5000 / 9999) * 9000, 5);
  });

  it('re-applies the position as images load (layout shift) and waits for them', async () => {
    setup('/ler/bk-1', { locator: 5000 });
    const frame = await openFrame();
    const chapter = mountChapter(frame, {
      html: '<img id="i" src="/api/v1/items/bk-1/book/res/a">',
      scrollHeight: 2000,
      skipLoad: true,
    });
    const image = chapter.doc.getElementById('i') as HTMLImageElement;
    Object.defineProperty(image, 'complete', { configurable: true, value: false });
    fireEvent.load(frame);
    expect(chapter.top()).toBeCloseTo((5000 / 9999) * 1000, 5);
    chapter.setScrollHeight(11000); // the image arrived and pushed the content down
    act(() => {
      image.dispatchEvent(new Event('load'));
    });
    expect(chapter.top()).toBeCloseTo((5000 / 9999) * 10000, 5);
  });

  it('a saved chapter beyond the book is clamped to the last chapter', async () => {
    setup('/ler/bk-1', { locator: 99 * 10000 + 10 });
    expect(await openFrame()).toHaveAttribute('src', chapterSrc(2));
  });
});

describe('EPUB reader: saving progress', () => {
  beforeEach(() => fakeApi.reset());

  it('first visit registers the beginning of the book', async () => {
    setup();
    mountChapter(await openFrame());
    await waitFor(() => expect(progressPuts()).toHaveLength(1), { timeout: 3000 });
    expect(progressPuts()[0]!.body).toEqual({ locator: 0 });
  });

  it('does not re-send the position it just restored (no change = no write)', async () => {
    setup('/ler/bk-1', { locator: 10000 + 5000 });
    const chapter = mountChapter(await openFrame());
    chapter.scrollTo(chapter.top()); // the scroll event caused by the restore itself
    await new Promise((resolve) => setTimeout(resolve, 1000));
    expect(progressPuts()).toHaveLength(0);
  });

  it('saves chapter*10000+offset after the user scrolls (debounced)', async () => {
    setup('/ler/bk-1', { locator: 10000 + 5000 });
    const chapter = mountChapter(await openFrame());
    chapter.userScrollTo(4500);
    chapter.userScrollTo(6300);
    expect(progressPuts()).toHaveLength(0); // still inside the debounce window
    await waitFor(() => expect(progressPuts()).toHaveLength(1), { timeout: 3000 });
    expect(progressPuts()[0]!.body).toEqual({ locator: 10000 + 6999 });
  });

  it('never saves a position lower than where it opened without a user gesture', async () => {
    setup('/ler/bk-1', { locator: 10000 + 5000 });
    const chapter = mountChapter(await openFrame());
    chapter.scrollTo(0); // layout shift / unfinished restore, not the user
    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(progressPuts()).toHaveLength(0);
    chapter.userScrollTo(0); // the user really went back
    await waitFor(() => expect(progressPuts()).toHaveLength(1), { timeout: 3000 });
    expect(progressPuts()[0]!.body).toEqual({ locator: 10000 });
  });

  it('flushes the pending position when the page is hidden (keepalive)', async () => {
    setup('/ler/bk-1', { locator: 10000 + 5000 });
    const chapter = mountChapter(await openFrame());
    chapter.userScrollTo(7200);
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    try {
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
      await waitFor(() => expect(progressPuts()).toHaveLength(1));
    } finally {
      Reflect.deleteProperty(document, 'visibilityState');
    }
    expect(progressPuts()[0]!.keepalive).toBe(true);
    expect(progressPuts()[0]!.body).toEqual({ locator: 10000 + Math.round((7200 / 9000) * 9999) });
  });

  it('saves the new position right away when the chapter changes', async () => {
    setup('/ler/bk-1', { locator: 10000 + 5000 });
    mountChapter(await openFrame());
    await userEvent.setup().click(screen.getByTestId('chapter-next'));
    await waitFor(() => expect(progressPuts()).toHaveLength(1), { timeout: 3000 });
    expect(progressPuts()[0]!.body).toEqual({ locator: 20000 });
  });

  it('a failed save does not break the reading and warns the user', async () => {
    setup('/ler/bk-1', { locator: 10000, progressPut: apiError(500) });
    const chapter = mountChapter(await openFrame());
    chapter.userScrollTo(3000);
    expect(await screen.findByTestId('save-warning', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByTestId('epub-frame')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByTestId('chapter-next'));
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(2));
  });
});

describe('EPUB reader: reading settings', () => {
  beforeEach(() => fakeApi.reset());

  async function openSettings() {
    const frame = await openFrame();
    const chapter = mountChapter(frame);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('open-settings'));
    return { user, chapter, frame };
  }

  it('A+ / A- change the size in steps, save the FULL object and reload the iframe', async () => {
    setup('/ler/bk-1', { prefs: { ...PREFS, theme: 'dark', reading_direction: 'ltr' } });
    const { user } = await openSettings();
    await user.click(screen.getByTestId('font-larger'));
    expect(screen.getByTestId('font-value')).toHaveTextContent('110%');
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(0, 'auto', 110));
    await waitFor(() => expect(prefPuts()).toHaveLength(1));
    expect(prefPuts()[0]!.body).toEqual({
      theme: 'dark',
      reading_direction: 'ltr',
      book_font_scale: 110,
      book_theme: 'auto',
    });
    await user.click(screen.getByTestId('font-smaller'));
    await user.click(screen.getByTestId('font-smaller'));
    expect(screen.getByTestId('font-value')).toHaveTextContent('90%');
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(0, 'auto', 90));
  });

  it('stops at the limits (80 and 200)', async () => {
    setup('/ler/bk-1', { prefs: { ...PREFS, book_font_scale: 200 } });
    const { user } = await openSettings();
    expect(screen.getByTestId('font-larger')).toBeDisabled();
    for (let i = 0; i < 12; i += 1) {
      if (screen.getByTestId('font-smaller').hasAttribute('disabled')) break;
      await user.click(screen.getByTestId('font-smaller'));
    }
    expect(screen.getByTestId('font-value')).toHaveTextContent('80%');
    expect(screen.getByTestId('font-smaller')).toBeDisabled();
    expect(screen.getByTestId('epub-frame').getAttribute('src')).toContain('size=80');
  });

  it('the book theme is saved and applied through the src', async () => {
    setup();
    const { user } = await openSettings();
    for (const theme of ['light', 'dark', 'sepia', 'auto']) {
      await user.click(screen.getByTestId(`book-theme-${theme}`));
      expect(screen.getByTestId(`book-theme-${theme}`)).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(0, theme));
    }
    await waitFor(() => expect(prefPuts().length).toBeGreaterThan(0));
    expect(prefPuts().at(-1)!.body).toEqual(PREFS);
  });

  it('keeps the reading position when the iframe reloads with new settings', async () => {
    setup('/ler/bk-1', { locator: 10000 + 5000 });
    const frame = await openFrame();
    const chapter = mountChapter(frame);
    chapter.userScrollTo(6300);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('open-settings'));
    await user.click(screen.getByTestId('book-theme-dark'));
    // the browser reloads the document: the geometry starts over, the position must come back
    const reloaded = mountChapter(frame);
    expect(reloaded.top()).toBeCloseTo((6999 / 9999) * 9000, 5);
  });

  it('does not write anything until the preferences GET answered', async () => {
    let release: (value: unknown) => void = () => undefined;
    setup('/ler/bk-1', { prefs: () => new Promise((resolve) => (release = resolve)) });
    // the book data arrives, but the preferences are still pending: the reader keeps waiting
    await waitFor(() => expect(fakeApi.callsTo('GET', '/api/v1/items/bk-1/book')).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.getByTestId('reader-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('epub-frame')).not.toBeInTheDocument();
    expect(prefPuts()).toHaveLength(0);
    release({ ...PREFS, book_font_scale: 150 });
    expect(await openFrame()).toHaveAttribute('src', chapterSrc(0, 'auto', 150));
    expect(prefPuts()).toHaveLength(0);
  });

  it('when the GET fails, changes are queued (never a PUT built from defaults)', async () => {
    let attempts = 0;
    setup('/ler/bk-1', {
      prefs: () => {
        attempts += 1;
        throw new ApiError(503, 'busy');
      },
    });
    const { user } = await openSettings();
    expect(attempts).toBeGreaterThan(0);
    expect(await screen.findByTestId('prefs-warning')).toHaveTextContent('carregar');
    await user.click(screen.getByTestId('font-larger'));
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(0, 'auto', 110));
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(prefPuts()).toHaveLength(0);
  });

  it('warns when saving the settings fails but keeps them applied', async () => {
    setup('/ler/bk-1');
    fakeApi.on('PUT', '/api/v1/me/preferences', apiError(500));
    const { user } = await openSettings();
    await user.click(screen.getByTestId('font-larger'));
    expect(await screen.findByTestId('prefs-warning')).toHaveTextContent('salvar');
    expect(screen.getByTestId('font-value')).toHaveTextContent('110%');
  });

  it('the settings panel closes with Esc', async () => {
    setup();
    await openSettings();
    expect(screen.getByRole('dialog', { name: 'Ajustes de leitura' })).toBeInTheDocument();
    await userEvent.setup().keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('EPUB reader: end of chapter and of the book', () => {
  beforeEach(() => fakeApi.reset());

  it('offers "Próximo capítulo" at the end of a chapter', async () => {
    setup();
    const chapter = mountChapter(await openFrame());
    expect(screen.queryByTestId('chapter-end')).not.toBeInTheDocument();
    chapter.userScrollTo(8990);
    await userEvent.setup().click(await screen.findByTestId('end-next-chapter'));
    expect(screen.getByTestId('epub-frame')).toHaveAttribute('src', chapterSrc(1));
  });

  it('at the end of the book: message and shortcut to the next book of the series', async () => {
    setup('/ler/bk-1?serie=serie-1', { locator: 2 * 10000, series: true });
    const chapter = mountChapter(await openFrame());
    chapter.userScrollTo(9000);
    expect(await screen.findByTestId('book-finished')).toHaveTextContent('fim do livro');
    await waitFor(() =>
      expect(screen.getByTestId('next-book')).toHaveAttribute('href', '/ler/bk-2?serie=serie-1'),
    );
    expect(screen.queryByTestId('end-next-chapter')).not.toBeInTheDocument();
    expect(screen.getByTestId('reader-back')).toHaveAttribute('href', '/serie/serie-1');
  });

  it('at the end of a standalone book there is no next-book shortcut', async () => {
    setup('/ler/bk-1', { locator: 2 * 10000 });
    const chapter = mountChapter(await openFrame());
    chapter.userScrollTo(9000);
    expect(await screen.findByTestId('book-finished')).toBeInTheDocument();
    expect(screen.queryByTestId('next-book')).not.toBeInTheDocument();
    expect(screen.getByTestId('reader-back')).toHaveAttribute('href', '/');
  });
});

describe('EPUB reader: reading mode switch', () => {
  beforeEach(() => fakeApi.reset());

  it('switching to vertical and back keeps the chapter being read, not the one it opened at', async () => {
    setup('/ler/bk-1', { locator: null, prefs: PREFS });
    await openFrame();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('chapter-next'));
    await user.click(screen.getByTestId('chapter-next'));
    expect(screen.getByTestId('chapter-indicator')).toHaveTextContent('Capítulo 3 de 3');
    await user.click(screen.getByTestId('open-settings'));
    await user.click(screen.getByTestId('reader-mode-vertical'));
    expect(await screen.findByTestId('epub-strip')).toBeInTheDocument();
    expect(screen.getByTestId('chapter-indicator')).toHaveTextContent('Capítulo 3 de 3');
    await user.click(screen.getByTestId('open-settings'));
    await user.click(screen.getByTestId('reader-mode-ltr'));
    expect(await openFrame()).toHaveAttribute('src', chapterSrc(2));
    expect(screen.getByTestId('chapter-indicator')).toHaveTextContent('Capítulo 3 de 3');
    await waitFor(() => expect(prefPuts().length).toBeGreaterThan(0));
    expect(prefPuts().at(-1)!.body).toMatchObject({ reading_direction: 'ltr' });
  });

  it('the slider is not mirrored for text (the direction is not honored yet)', async () => {
    setup('/ler/bk-1', { prefs: PREFS });
    await openFrame();
    expect(screen.getByTestId('chapter-slider')).toHaveAttribute('dir', 'ltr');
  });
});
