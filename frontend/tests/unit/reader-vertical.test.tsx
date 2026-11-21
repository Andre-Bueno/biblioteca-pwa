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

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const putCalls = () => fakeApi.callsTo('PUT', /^\/api\/v1\/progress\/item-1$/);
const indicator = () => screen.getByTestId('page-indicator');

// Minimal IntersectionObserver: tests decide which page "crosses the middle of the screen".
interface FakeObserver {
  callback: IntersectionObserverCallback;
  elements: Element[];
  active: boolean;
}
let observers: FakeObserver[] = [];

function stubIntersectionObserver() {
  observers = [];
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      state: FakeObserver;
      constructor(callback: IntersectionObserverCallback) {
        this.state = { callback, elements: [], active: true };
        observers.push(this.state);
      }
      observe(element: Element) {
        this.state.elements.push(element);
      }
      unobserve() {}
      disconnect() {
        this.state.active = false;
      }
    },
  );
}

function intersect(page: number) {
  const live = observers.filter((o) => o.active).at(-1)!;
  const target = live.elements.find((el) => (el as HTMLElement).dataset.page === String(page))!;
  act(() => {
    live.callback(
      [{ isIntersecting: true, target } as unknown as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
  });
}

async function openReader({
  saved = null,
  direction = 'vertical',
  pages = 10,
  type = 'manga',
}: {
  saved?: number | null;
  direction?: 'rtl' | 'ltr' | 'vertical';
  pages?: number;
  type?: string;
} = {}) {
  signedIn();
  fakeApi.on('GET', '/api/v1/me/preferences', { theme: 'system', reading_direction: direction });
  fakeApi.on('GET', '/api/v1/items/item-1', makeItem({ page_count: pages, type }));
  fakeApi.on('GET', '/api/v1/progress/item-1', () => {
    if (saved === null) throw new ApiError(404, 'none');
    return { item_id: 'item-1', locator: saved, percent: 10, finished: false, updated_at: 'x' };
  });
  fakeApi.on('PUT', '/api/v1/progress/item-1', ({ body }) => body);
  renderApp('/ler/item-1');
  return screen.findByTestId(type === 'manga' ? 'reader' : 'reader-message', {}, { timeout: 3000 });
}

describe('vertical reader: resume must not regress the saved progress', () => {
  beforeEach(() => {
    fakeApi.reset();
    stubIntersectionObserver();
  });
  afterEach(() => vi.unstubAllGlobals());

  it('ignores earlier pages reported by layout shifts before the target is loaded', async () => {
    await openReader({ saved: 5 });
    await wait(450); // past the post-scroll suppression window
    intersect(0); // images above loaded and the observer saw page 0 under the middle line
    intersect(2);
    expect(indicator()).toHaveTextContent('6 / 10');
    await wait(1100);
    expect(putCalls()).toHaveLength(0); // nothing lower than the saved page was written
  });

  it('after the target page loaded: later pages count, earlier ones still do not', async () => {
    await openReader({ saved: 5 });
    const target = within(screen.getAllByTestId('strip-page')[5]!).getByRole('img');
    fireEvent.load(target); // positioned
    await wait(450);
    intersect(2); // layout shift: below the initial page, no user gesture
    expect(indicator()).toHaveTextContent('6 / 10');
    intersect(6); // the user-less drift forward is accepted (>= initial)
    expect(indicator()).toHaveTextContent('7 / 10');
    await waitFor(() => expect(putCalls()).toHaveLength(1), { timeout: 2500 });
    expect(putCalls()[0]!.body).toEqual({ locator: 6 });
  });

  it('after a user scroll gesture any page is accepted, including going back', async () => {
    await openReader({ saved: 5 });
    fireEvent.wheel(window, { deltaY: -100 });
    await wait(450);
    intersect(2);
    expect(indicator()).toHaveTextContent('3 / 10');
    await waitFor(() => expect(putCalls().at(-1)?.body).toEqual({ locator: 2 }), {
      timeout: 2500,
    });
  });

  it('touch scrolling and scroll keys also count as a gesture', async () => {
    await openReader({ saved: 5 });
    fireEvent.touchMove(window);
    await wait(450);
    intersect(3);
    expect(indicator()).toHaveTextContent('4 / 10');
  });
});

describe('vertical reader: windowed pages', () => {
  beforeEach(() => {
    fakeApi.reset();
    stubIntersectionObserver();
  });
  afterEach(() => vi.unstubAllGlobals());

  it('mounts only the pages around the current one, keeping a placeholder for the rest', async () => {
    await openReader({ saved: 10, pages: 30 });
    const pages = screen.getAllByTestId('strip-page');
    expect(pages).toHaveLength(30); // all slots exist (scroll height / observer targets)
    const mounted = pages.filter((el) => el.dataset.mounted === 'true');
    expect(mounted).toHaveLength(7);
    expect(mounted.map((el) => el.dataset.page)).toEqual(['7', '8', '9', '10', '11', '12', '13']);
    expect(screen.getAllByRole('img')).toHaveLength(7);
  });

  it('moves the window with the current page', async () => {
    await openReader({ saved: 10, pages: 30 });
    fireEvent.wheel(window);
    await wait(450);
    intersect(20);
    const mounted = screen
      .getAllByTestId('strip-page')
      .filter((el) => el.dataset.mounted === 'true')
      .map((el) => el.dataset.page);
    expect(mounted).toEqual(['17', '18', '19', '20', '21', '22', '23']);
    expect(screen.getAllByRole('img')).toHaveLength(7);
  });
});

describe('reader: memory and accessibility', () => {
  beforeEach(() => fakeApi.reset());
  afterEach(() => vi.unstubAllGlobals());

  it('drops preloaded pages behind page-2 and ahead of the lookahead (bounded cache)', async () => {
    const srcs: string[] = [];
    vi.stubGlobal(
      'Image',
      class {
        decoding = '';
        set src(value: string) {
          srcs.push(value);
        }
      },
    );
    await openReader({ saved: 4, direction: 'rtl', pages: 30 });
    expect(srcs).toEqual(['/api/v1/items/item-1/pages/5', '/api/v1/items/item-1/pages/6']);
    fireEvent.change(screen.getByTestId('page-slider'), { target: { value: '21' } }); // page 20
    expect(srcs.slice(2)).toEqual([
      '/api/v1/items/item-1/pages/21',
      '/api/v1/items/item-1/pages/22',
    ]);
    fireEvent.change(screen.getByTestId('page-slider'), { target: { value: '5' } }); // back to 4
    // 5 and 6 were evicted while far away, so they are requested again (from the HTTP cache).
    expect(srcs.slice(4)).toEqual(['/api/v1/items/item-1/pages/5', '/api/v1/items/item-1/pages/6']);
  });

  it('the page indicator is a polite live region', async () => {
    await openReader({ direction: 'rtl' });
    expect(indicator()).toHaveAttribute('aria-live', 'polite');
  });

  it('keyboard and button ways to bring the controls back', async () => {
    await openReader({ direction: 'rtl' });
    const user = userEvent.setup();
    fireEvent.keyDown(window, { key: 'm' });
    expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();
    await user.click(screen.getByTestId('show-controls'));
    expect(screen.getByTestId('reader-controls')).toBeInTheDocument();
    expect(screen.queryByTestId('show-controls')).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByTestId('reader-viewport'), { key: 'Enter' });
    expect(screen.queryByTestId('reader-controls')).not.toBeInTheDocument();
  });

  it('the viewport is focusable and has focusable prev/next controls', async () => {
    await openReader({ saved: 3, direction: 'rtl' });
    const viewport = screen.getByTestId('reader-viewport');
    expect(viewport).toHaveAttribute('tabindex', '0');
    expect(viewport).toHaveAttribute('aria-label', expect.stringContaining('Página 4 de 10'));
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Próxima página' }));
    expect(indicator()).toHaveTextContent('5 / 10');
    await user.click(screen.getByRole('button', { name: 'Página anterior' }));
    expect(indicator()).toHaveTextContent('4 / 10');
  });

  it('shows a clear message instead of broken images for formats not supported yet', async () => {
    await openReader({ type: 'pdf' });
    expect(await screen.findByTestId('reader-message')).toHaveTextContent(
      'Este formato ainda não é suportado.',
    );
    expect(screen.queryByTestId('reader')).not.toBeInTheDocument();
    expect(screen.queryAllByRole('img')).toHaveLength(0);
  });
});
