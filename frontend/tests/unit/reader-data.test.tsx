import { renderHook, waitFor } from '@testing-library/react';
import { act } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useReaderData } from '../../src/features/reader/hooks/useReaderData';
import { useReaderProgress } from '../../src/features/reader/hooks/useReaderProgress';
import { createBookChaptersSource } from '../../src/features/reader/sources/chaptersSource';
import { createImagePagesSource } from '../../src/features/reader/sources/pagesSource';
import { ApiError } from '../../src/shared/api-client/errors';
import { fakeApi, makeItem } from '../helpers/fake-api';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const BOOK = {
  title: 'Livro',
  authors: [],
  language: 'pt-BR',
  chapters: [
    { index: 0, title: 'A' },
    { index: 1, title: 'B' },
    { index: 2, title: 'C' },
  ],
  toc: [],
  has_cover: false,
};

function progress(locator: number) {
  return { item_id: 'x', locator, percent: 1, finished: false, updated_at: 'x' };
}

function routes(options: { type?: string; saved?: number | null; book?: () => unknown } = {}) {
  const { type = 'manga', saved = null } = options;
  fakeApi.on(
    'GET',
    '/api/v1/items/it-1',
    makeItem({ id: 'it-1', type, page_count: type === 'book' ? null : 10 }),
  );
  fakeApi.on('GET', '/api/v1/items/it-1/book', options.book ?? BOOK);
  fakeApi.on('GET', '/api/v1/progress/it-1', () => {
    if (saved === null) throw new ApiError(404, 'none');
    return progress(saved);
  });
}

describe('useReaderData', () => {
  beforeEach(() => fakeApi.reset());

  it('manga: pages source and the saved page decoded as a page', async () => {
    routes({ saved: 5 });
    const { result } = renderHook(() => useReaderData('it-1'));
    expect(result.current.data.status).toBe('loading');
    await waitFor(() => expect(result.current.data.status).toBe('ready'));
    const data = result.current.data;
    if (data.status !== 'ready') throw new Error('not ready');
    expect(data.source.kind).toBe('pages');
    expect(data.savedLocator).toBe(5);
    expect(data.savedPosition).toEqual({ unit: 5, bp: 0 });
    expect(data.book).toBeNull();
    expect(fakeApi.callsTo('GET', '/api/v1/items/it-1/book')).toHaveLength(0);
  });

  it('book: chapters source; 2 * 10000 + 2500 decodes to chapter 2 at 25%', async () => {
    routes({ type: 'book', saved: 22500 });
    const { result } = renderHook(() => useReaderData('it-1'));
    await waitFor(() => expect(result.current.data.status).toBe('ready'));
    const data = result.current.data;
    if (data.status !== 'ready') throw new Error('not ready');
    expect(data.source.kind).toBe('chapters');
    expect(data.savedPosition).toEqual({ unit: 2, bp: 2500 });
  });

  it('clamps a position beyond the end and drops the offset', async () => {
    routes({ type: 'book', saved: 9 * 10000 + 500 });
    const { result } = renderHook(() => useReaderData('it-1'));
    await waitFor(() => expect(result.current.data.status).toBe('ready'));
    const data = result.current.data;
    if (data.status !== 'ready') throw new Error('not ready');
    expect(data.savedPosition).toEqual({ unit: 2, bp: 0 });
  });

  it('no saved progress (404) means null locator and the first position', async () => {
    routes({ saved: null });
    const { result } = renderHook(() => useReaderData('it-1'));
    await waitFor(() => expect(result.current.data.status).toBe('ready'));
    const data = result.current.data;
    if (data.status !== 'ready') throw new Error('not ready');
    expect(data.savedLocator).toBeNull();
    expect(data.savedPosition).toEqual({ unit: 0, bp: 0 });
  });

  it('a book that is not found says so; PDF is unsupported', async () => {
    routes({
      type: 'book',
      book: () => {
        throw new ApiError(404, 'x');
      },
    });
    const first = renderHook(() => useReaderData('it-1'));
    await waitFor(() =>
      expect(first.result.current.data).toEqual({ status: 'notfound', subject: 'book' }),
    );
    routes({ type: 'pdf' });
    const second = renderHook(() => useReaderData('it-1'));
    await waitFor(() => expect(second.result.current.data.status).toBe('unsupported'));
  });

  it('retry after a failed book reloads the book once and the item not at all', async () => {
    let attempts = 0;
    routes({
      type: 'book',
      book: () => {
        attempts += 1;
        if (attempts === 1) throw new ApiError(500, 'down');
        return BOOK;
      },
    });
    const { result } = renderHook(() => useReaderData('it-1'));
    await waitFor(() => expect(result.current.data.status).toBe('error'));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.data.status).toBe('ready'));
    await new Promise((resolve) => setTimeout(resolve, 50)); // a double load would show up here
    expect(fakeApi.callsTo('GET', '/api/v1/items/it-1/book')).toHaveLength(2);
    expect(fakeApi.callsTo('GET', '/api/v1/items/it-1')).toHaveLength(1);
    expect(fakeApi.callsTo('GET', '/api/v1/progress/it-1')).toHaveLength(2);
  });

  it('retry after the item itself failed loads it again, once', async () => {
    let attempts = 0;
    routes();
    fakeApi.on('GET', '/api/v1/items/it-1', () => {
      attempts += 1;
      if (attempts === 1) throw new ApiError(500, 'down');
      return makeItem({ id: 'it-1', type: 'manga', page_count: 10 });
    });
    const { result } = renderHook(() => useReaderData('it-1'));
    await waitFor(() => expect(result.current.data.status).toBe('error'));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.data.status).toBe('ready'));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(fakeApi.callsTo('GET', '/api/v1/items/it-1')).toHaveLength(2);
    expect(fakeApi.callsTo('GET', '/api/v1/progress/it-1')).toHaveLength(1);
  });
});

describe('useReaderProgress', () => {
  beforeEach(() => {
    fakeApi.reset();
    fakeApi.on('PUT', '/api/v1/progress/it-1', ({ body }: { body: unknown }) => ({
      ...(body as object),
    }));
  });
  const puts = () => fakeApi.callsTo('PUT', '/api/v1/progress/it-1');
  const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  it('first visit registers the opening position (page 0)', async () => {
    const source = createImagePagesSource(10);
    renderHook(() => useReaderProgress('it-1', source, null, { unit: 0, bp: 0 }));
    await waitFor(() => expect(puts()).toHaveLength(1), { timeout: 2500 });
    expect(puts()[0]!.body).toEqual({ locator: 0 });
  });

  it('first visit to a book registers chapter * 10000 + bp', async () => {
    const source = createBookChaptersSource(BOOK);
    renderHook(() => useReaderProgress('it-1', source, null, { unit: 0, bp: 0 }));
    await waitFor(() => expect(puts()).toHaveLength(1), { timeout: 2500 });
    expect(puts()[0]!.body).toEqual({ locator: 0 });
  });

  it('the server value is the baseline: it is not sent back', async () => {
    const source = createImagePagesSource(10);
    const { result } = renderHook(() => useReaderProgress('it-1', source, 4, { unit: 4, bp: 0 }));
    act(() => result.current.reportPosition(4));
    await wait(1200);
    expect(puts()).toHaveLength(0);
  });

  it('a new position is encoded by the source codec and saved once', async () => {
    const source = createBookChaptersSource(BOOK);
    const { result } = renderHook(() =>
      useReaderProgress('it-1', source, 10000, { unit: 1, bp: 0 }),
    );
    act(() => result.current.reportPosition(2, 1500));
    await waitFor(() => expect(puts()).toHaveLength(1), { timeout: 2500 });
    expect(puts()[0]!.body).toEqual({ locator: 21500 });
  });
});
