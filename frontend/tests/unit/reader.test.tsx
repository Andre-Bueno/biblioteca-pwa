import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../src/shared/api-client/errors';
import { fakeApi, makeItem, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

// jsdom has no layout: getBoundingClientRect().width is 0, so the gesture hook uses innerWidth (1024).
const LEFT = 40;
const RIGHT = 980;
const CENTER = 512;

function pointer(el: Element, type: 'pointerdown' | 'pointerup', x: number, y = 300) {
  fireEvent(el, new MouseEvent(type, { bubbles: true, clientX: x, clientY: y }));
}
function tap(el: Element, x: number) {
  pointer(el, 'pointerdown', x);
  pointer(el, 'pointerup', x);
}
function swipe(el: Element, fromX: number, toX: number) {
  pointer(el, 'pointerdown', fromX);
  pointer(el, 'pointerup', toX);
}

const pageSrc = () => screen.getByTestId('reader-page-img').getAttribute('src');
const putCalls = () => fakeApi.callsTo('PUT', /^\/api\/v1\/progress\/item-1$/);

interface Options {
  saved?: number | null;
  direction?: 'rtl' | 'ltr' | 'vertical';
  pages?: number;
}

async function openReader({ saved = null, direction = 'rtl', pages = 10 }: Options = {}) {
  signedIn();
  fakeApi.on('GET', '/api/v1/me/preferences', { theme: 'system', reading_direction: direction });
  fakeApi.on('GET', '/api/v1/items/item-1', makeItem({ page_count: pages }));
  fakeApi.on('GET', '/api/v1/progress/item-1', () => {
    if (saved === null) throw new ApiError(404, 'none');
    return { item_id: 'item-1', locator: saved, percent: 10, finished: false, updated_at: 'x' };
  });
  fakeApi.on('PUT', '/api/v1/progress/item-1', ({ body }) => ({
    item_id: 'item-1',
    ...(body as object),
    percent: 0,
    finished: false,
    updated_at: 'x',
  }));
  renderApp('/ler/item-1');
  return screen.findByTestId('reader');
}

describe('manga reader', () => {
  beforeEach(() => fakeApi.reset());
  afterEach(() => vi.unstubAllGlobals());

  describe('resume', () => {
    it('opens at the saved page', async () => {
      await openReader({ saved: 4 });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/4');
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('5 / 10');
    });

    it('starts at page 1 when there is no progress (404)', async () => {
      await openReader({ saved: null });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/0');
    });

    it('clamps a locator beyond the end', async () => {
      await openReader({ saved: 999 });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/9');
    });

    it('shows a message for an unknown item, and for one without pages', async () => {
      signedIn();
      renderApp('/ler/missing');
      expect(await screen.findByTestId('reader-message')).toHaveTextContent('não encontrado');
    });

    it('does not open an item without pages', async () => {
      signedIn();
      fakeApi.on('GET', '/api/v1/items/item-1', makeItem({ page_count: 0 }));
      renderApp('/ler/item-1');
      expect(await screen.findByTestId('reader-message')).toHaveTextContent('não tem páginas');
    });
  });

  describe('paged right-to-left (default)', () => {
    it('left tap goes forward, right tap goes back', async () => {
      await openReader({ saved: 4 });
      const viewport = screen.getByTestId('reader-viewport');
      expect(viewport).toHaveAttribute('data-mode', 'rtl');
      tap(viewport, LEFT);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/5');
      tap(viewport, RIGHT);
      tap(viewport, RIGHT);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/3');
    });

    it('swiping right brings the next page; swiping left goes back', async () => {
      await openReader({ saved: 4 });
      const viewport = screen.getByTestId('reader-viewport');
      swipe(viewport, 100, 320);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/5');
      swipe(viewport, 320, 100);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/4');
    });

    it('does not go past the first or last page', async () => {
      await openReader({ saved: 9 });
      const viewport = screen.getByTestId('reader-viewport');
      tap(viewport, LEFT);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/9');
      fireEvent.keyDown(window, { key: 'Home' });
      tap(viewport, RIGHT);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/0');
    });

    it('keyboard: arrows follow the direction, Home/End jump', async () => {
      await openReader({ saved: 4 });
      fireEvent.keyDown(window, { key: 'ArrowLeft' });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/5');
      fireEvent.keyDown(window, { key: 'ArrowRight' });
      fireEvent.keyDown(window, { key: 'ArrowRight' });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/3');
      fireEvent.keyDown(window, { key: 'End' });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/9');
      fireEvent.keyDown(window, { key: 'Home' });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/0');
    });

    it('the slider jumps to a page and is mirrored (dir=rtl)', async () => {
      await openReader({ saved: 0 });
      const slider = screen.getByTestId('page-slider');
      expect(slider).toHaveAttribute('dir', 'rtl');
      fireEvent.change(slider, { target: { value: '6' } }); // 0-based: page 7
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/6');
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('7 / 10');
    });
  });

  describe('paged left-to-right', () => {
    it('right tap, right swipe-left and ArrowRight go forward', async () => {
      await openReader({ saved: 4, direction: 'ltr' });
      const viewport = screen.getByTestId('reader-viewport');
      expect(viewport).toHaveAttribute('data-mode', 'ltr');
      tap(viewport, RIGHT);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/5');
      swipe(viewport, 320, 100); // swipe left
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/6');
      fireEvent.keyDown(window, { key: 'ArrowRight' });
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/7');
      tap(viewport, LEFT);
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/6');
      expect(screen.getByTestId('page-slider')).toHaveAttribute('dir', 'ltr');
    });
  });

  describe('vertical (webtoon)', () => {
    it('renders every page lazily in a strip and keeps edge taps from turning pages', async () => {
      await openReader({ direction: 'vertical', saved: 2 });
      const pages = screen.getAllByTestId('strip-page');
      expect(pages).toHaveLength(10);
      const img = within(pages[3]!).getByRole('img');
      expect(img).toHaveAttribute('src', '/api/v1/items/item-1/pages/3');
      expect(img).toHaveAttribute('loading', 'lazy');
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('3 / 10'); // resumed at saved page
      tap(screen.getByTestId('reader-strip'), LEFT);
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('3 / 10');
    });

    it('a tap toggles the controls at once (no double-tap wait)', async () => {
      await openReader({ direction: 'vertical' });
      expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
      tap(screen.getByTestId('reader-strip'), CENTER);
      expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();
    });

    it('scrolls to the page chosen with the slider', async () => {
      const scrollIntoView = vi.fn();
      Element.prototype.scrollIntoView = scrollIntoView;
      await openReader({ direction: 'vertical' });
      scrollIntoView.mockClear();
      fireEvent.change(screen.getByTestId('page-slider'), { target: { value: '5' } }); // 0-based: page 6
      expect(scrollIntoView).toHaveBeenCalledTimes(1);
      expect((scrollIntoView.mock.contexts[0] as HTMLElement).dataset.page).toBe('5');
      // @ts-expect-error restore jsdom's lack of scrollIntoView
      delete Element.prototype.scrollIntoView;
    });
  });

  describe('modes and controls', () => {
    it('switches between the three modes in the reader, keeping the page', async () => {
      await openReader({ saved: 4 });
      const user = userEvent.setup();
      await user.click(screen.getByTestId('open-settings')); // the mode lives in the Aa panel
      await user.click(screen.getByTestId('reader-mode-vertical'));
      expect(screen.getByTestId('reader-strip')).toBeInTheDocument();
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('5 / 10');
      await user.click(screen.getByTestId('reader-mode-ltr'));
      expect(screen.getByTestId('reader-viewport')).toHaveAttribute('data-mode', 'ltr');
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/4');
      await user.click(screen.getByTestId('reader-mode-rtl'));
      expect(screen.getByTestId('reader-viewport')).toHaveAttribute('data-mode', 'rtl');
    });

    it('a centre tap hides and shows the controls; there is a back button', async () => {
      await openReader();
      expect(screen.getByTestId('reader-back')).toHaveAttribute('href', '/');
      const viewport = screen.getByTestId('reader-viewport');
      tap(viewport, CENTER);
      await waitFor(() => expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument());
      expect(screen.getByTestId('page-indicator')).toBeInTheDocument(); // stays visible
      tap(viewport, CENTER);
      expect(await screen.findByTestId('reader-controls')).toBeInTheDocument();
    });

    it('double tap in the centre zooms (and back); the zoom button does the same', async () => {
      await openReader();
      const viewport = screen.getByTestId('reader-viewport');
      tap(viewport, CENTER);
      tap(viewport, CENTER);
      expect(viewport).toHaveAttribute('data-zoomed', 'true');
      expect(screen.getByTestId('reader-controls')).toBeInTheDocument(); // no single-tap toggle
      await userEvent.setup().click(screen.getByTestId('zoom-toggle'));
      expect(viewport).toHaveAttribute('data-zoomed', 'false');
    });

    it('on a touch device the bars start hidden, a "n / N" pill shows, and m or the button bring them back', async () => {
      vi.stubGlobal(
        'matchMedia',
        vi.fn((query: string) => ({
          matches: query.includes('pointer: coarse'),
          media: query,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
        })),
      );
      await openReader({ saved: 4 });
      expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();
      expect(screen.getByTestId('page-indicator')).toHaveTextContent('5 / 10');
      fireEvent.keyDown(window, { key: 'm' });
      expect(await screen.findByTestId('reader-controls')).toBeInTheDocument();
      expect(screen.getByTestId('open-settings')).toBeInTheDocument();
      expect(screen.queryByTestId('open-toc')).not.toBeInTheDocument(); // pages have no index
    });

    it('the Aa panel holds the reading mode but no font or theme for pages', async () => {
      await openReader();
      await userEvent.setup().click(screen.getByTestId('open-settings'));
      expect(screen.getByTestId('reader-mode')).toBeInTheDocument();
      expect(screen.queryByTestId('font-larger')).not.toBeInTheDocument();
      expect(screen.queryByTestId('book-theme')).not.toBeInTheDocument();
    });

    it('turning the page resets the zoom', async () => {
      await openReader({ saved: 2 });
      const viewport = screen.getByTestId('reader-viewport');
      await userEvent.setup().click(screen.getByTestId('zoom-toggle'));
      expect(viewport).toHaveAttribute('data-zoomed', 'true');
      fireEvent.keyDown(window, { key: 'ArrowLeft' });
      expect(viewport).toHaveAttribute('data-zoomed', 'false');
    });
  });

  describe('preload', () => {
    function stubImage() {
      const srcs: string[] = [];
      class FakeImage {
        decoding = '';
        set src(value: string) {
          srcs.push(value);
        }
      }
      vi.stubGlobal('Image', FakeImage);
      return srcs;
    }

    it('preloads the next 2 pages and only the new one when advancing', async () => {
      const srcs = stubImage();
      await openReader({ saved: 4 });
      expect(srcs).toEqual(['/api/v1/items/item-1/pages/5', '/api/v1/items/item-1/pages/6']);
      fireEvent.keyDown(window, { key: 'ArrowLeft' }); // page 5 -> needs 6 (have) and 7
      expect(srcs.slice(2)).toEqual(['/api/v1/items/item-1/pages/7']);
    });

    it('stops at the last page and does not preload in vertical mode', async () => {
      const srcs = stubImage();
      await openReader({ saved: 8 });
      expect(srcs).toEqual(['/api/v1/items/item-1/pages/9']);
    });

    it('vertical mode relies on lazy loading instead of preloading', async () => {
      const srcs = stubImage();
      await openReader({ direction: 'vertical', saved: 3 });
      expect(srcs).toEqual([]);
    });
  });

  describe('saving progress', () => {
    it('debounces: several page turns produce ONE save with the last page', async () => {
      await openReader({ saved: 4 });
      const viewport = screen.getByTestId('reader-viewport');
      tap(viewport, LEFT);
      tap(viewport, LEFT);
      expect(putCalls()).toHaveLength(0); // nothing sent while the user keeps turning
      await waitFor(() => expect(putCalls()).toHaveLength(1), { timeout: 2500 });
      expect(putCalls()[0]!.body).toEqual({ locator: 6 });
      expect(putCalls()[0]!.keepalive).toBe(false);
      await new Promise((resolve) => setTimeout(resolve, 1000));
      expect(putCalls()).toHaveLength(1);
    });

    it('registers page 1 for an item that was never read', async () => {
      await openReader({ saved: null });
      await waitFor(() => expect(putCalls()).toHaveLength(1), { timeout: 2500 });
      expect(putCalls()[0]!.body).toEqual({ locator: 0 });
    });

    it('does not re-send the page the server already has', async () => {
      await openReader({ saved: 4 });
      await new Promise((resolve) => setTimeout(resolve, 1100));
      expect(putCalls()).toHaveLength(0);
    });

    it('flushes immediately on pagehide with fetch keepalive (never sendBeacon)', async () => {
      const beacon = vi.fn();
      vi.stubGlobal('navigator', { ...globalThis.navigator, sendBeacon: beacon });
      await openReader({ saved: 4 });
      tap(screen.getByTestId('reader-viewport'), LEFT);
      expect(putCalls()).toHaveLength(0);
      act(() => {
        window.dispatchEvent(new Event('pagehide'));
      });
      expect(putCalls()).toHaveLength(1);
      expect(putCalls()[0]).toMatchObject({ body: { locator: 5 }, keepalive: true });
      expect(beacon).not.toHaveBeenCalled();
    });

    it('flushes when the page becomes hidden (visibilitychange)', async () => {
      await openReader({ saved: 4 });
      tap(screen.getByTestId('reader-viewport'), LEFT);
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
      expect(putCalls()).toHaveLength(1);
      expect(putCalls()[0]).toMatchObject({ body: { locator: 5 }, keepalive: true });
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    });

    it('flushes when leaving the reader', async () => {
      await openReader({ saved: 4 });
      tap(screen.getByTestId('reader-viewport'), LEFT);
      await userEvent.setup().click(screen.getByTestId('reader-back'));
      await waitFor(() => expect(screen.getByTestId('library-page')).toBeInTheDocument());
      expect(putCalls()).toHaveLength(1);
      expect(putCalls()[0]).toMatchObject({ body: { locator: 5 }, keepalive: true });
    });

    it('a failed save shows a discreet warning, keeps reading and retries', async () => {
      await openReader({ saved: 4 });
      let failing = true;
      fakeApi.on('PUT', '/api/v1/progress/item-1', ({ body }) => {
        if (failing) throw new ApiError(500, 'down');
        return { item_id: 'item-1', ...(body as object) };
      });
      const viewport = screen.getByTestId('reader-viewport');
      tap(viewport, LEFT);
      expect(await screen.findByTestId('save-warning', {}, { timeout: 2500 })).toBeInTheDocument();
      tap(viewport, LEFT); // reading is not interrupted
      expect(pageSrc()).toBe('/api/v1/items/item-1/pages/6');
      failing = false;
      act(() => {
        window.dispatchEvent(new Event('pagehide')); // flush stands in for the 5 s retry timer
      });
      await waitFor(() => expect(screen.queryByTestId('save-warning')).not.toBeInTheDocument());
      expect(putCalls().at(-1)!.body).toEqual({ locator: 6 });
    });
  });
});

describe('manga reader: bars on a touch device', () => {
  beforeEach(() => fakeApi.reset());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function stubTouch() {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query.includes('pointer: coarse'),
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      })),
    );
  }

  it('hide by themselves 4 s after being shown, but not while the slider is held', async () => {
    stubTouch();
    await openReader({ saved: 4 });
    vi.useFakeTimers({ shouldAdvanceTime: false });
    fireEvent.keyDown(window, { key: 'm' });
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(3900));
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(200));
    expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'm' });
    const slider = screen.getByTestId('page-slider');
    fireEvent.pointerDown(slider);
    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument(); // held: stays up
    fireEvent.pointerUp(slider);
    act(() => vi.advanceTimersByTime(4100));
    expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();
  });

  it('switching the mode in the panel keeps the page and is saved as a preference', async () => {
    await openReader({ saved: 4 });
    const user = userEvent.setup();
    await user.click(screen.getByTestId('open-settings'));
    await user.click(screen.getByTestId('reader-mode-ltr'));
    expect(pageSrc()).toBe('/api/v1/items/item-1/pages/4');
    await waitFor(() =>
      expect(fakeApi.callsTo('PUT', '/api/v1/me/preferences').at(-1)?.body).toMatchObject({
        reading_direction: 'ltr',
      }),
    );
  });
});
