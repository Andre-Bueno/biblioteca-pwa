import { screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  fakeApi,
  makeChapter,
  makeItem,
  makeSeries,
  makeSeriesDetail,
  signedIn,
} from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const book = (n: number, overrides: Record<string, unknown> = {}) =>
  makeChapter(n, {
    id: `bk-${n}`,
    title: `Livro ${n}`,
    type: 'book',
    page_count: null,
    ...overrides,
  });

describe('series made of books', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it('the series page labels volumes "Livro" (no page count) and shows progress in %', async () => {
    fakeApi.on(
      'GET',
      '/api/v1/series/serie-1',
      makeSeriesDetail({
        chapter_count: 3,
        chapters: [
          book(1, { progress: { locator: 50000, percent: 100, finished: true } }),
          book(2, { progress: { locator: 12500, percent: 40, finished: false } }),
          book(3),
        ],
      }),
    );
    renderApp('/serie/serie-1');
    const rows = await screen.findAllByTestId('chapter-row');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('Livro · Concluído');
    expect(rows[1]).toHaveTextContent('Livro · Em andamento (40%)');
    expect(rows[2]).toHaveTextContent('Livro · Não lido');
    for (const row of rows) expect(row).not.toHaveTextContent(/página/);
    expect(within(rows[1]!).getByRole('progressbar')).toHaveAttribute('value', '40');
    expect(screen.getByTestId('series-count')).toHaveTextContent('3 livros');
    expect(screen.getByText('Livros')).toBeInTheDocument();
    expect(rows[1]).toHaveAttribute('href', '/ler/bk-2?serie=serie-1');
  });

  it('manga chapters keep the page count; older servers without `type` still work', async () => {
    fakeApi.on(
      'GET',
      '/api/v1/series/serie-1',
      makeSeriesDetail({ chapters: [makeChapter(1), makeChapter(2, { page_count: 1 })] }),
    );
    renderApp('/serie/serie-1');
    const rows = await screen.findAllByTestId('chapter-row');
    expect(rows[0]).toHaveTextContent('10 páginas');
    expect(rows[1]).toHaveTextContent('1 página');
    expect(rows[0]).not.toHaveTextContent('Livro');
  });

  it('older servers (no kind): a mixed series is derived as "itens"', async () => {
    fakeApi.on(
      'GET',
      '/api/v1/series/serie-1',
      makeSeriesDetail({ chapters: [makeChapter(1), book(2)] }),
    );
    renderApp('/serie/serie-1');
    expect(await screen.findByTestId('series-count')).toHaveTextContent('3 itens');
  });

  it.each([
    ['book', '3 livros', 'Livros'],
    ['manga', '3 capítulos', 'Capítulos'],
    ['mixed', '3 itens', 'Itens'],
  ])('the server `kind` (%s) drives the header and the list title', async (kind, count, title) => {
    // chapters deliberately say the opposite: `kind` wins
    fakeApi.on(
      'GET',
      '/api/v1/series/serie-1',
      makeSeriesDetail({ kind, chapters: [makeChapter(1), makeChapter(2)] }),
    );
    renderApp('/serie/serie-1');
    expect(await screen.findByTestId('series-count')).toHaveTextContent(count);
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
  });

  it('the chapter `type` wins over the page count; the fallback is only for old answers', async () => {
    fakeApi.on(
      'GET',
      '/api/v1/series/serie-1',
      makeSeriesDetail({
        kind: 'mixed',
        chapters: [
          makeChapter(1, { type: 'book', page_count: 12 }),
          makeChapter(2, { type: 'manga', page_count: 7 }),
          makeChapter(3, { type: 'pdf', page_count: null }),
          makeChapter(4, { type: undefined, page_count: null }),
        ],
      }),
    );
    renderApp('/serie/serie-1');
    const rows = await screen.findAllByTestId('chapter-row');
    expect(rows[0]).toHaveTextContent('Livro');
    expect(rows[1]).toHaveTextContent('7 páginas');
    expect(rows[2]).not.toHaveTextContent('Livro');
    expect(rows[3]).toHaveTextContent('Livro'); // no `type` at all: old server fallback
  });

  it.each([
    ['book', 1, '1 livro'],
    ['book', 4, '4 livros'],
    ['manga', 4, '4 capítulos'],
    ['mixed', 1, '1 item'],
    ['mixed', 4, '4 itens'],
    [undefined, 2, '2 capítulos'],
  ])('the library card with kind %s and %i items says "%s"', async (kind, count, label) => {
    fakeApi.on('GET', '/api/v1/series', {
      items: [makeSeries({ id: 'serie-9', title: 'Saga', chapter_count: count, kind })],
      limit: 30,
      offset: 0,
      has_more: false,
    });
    renderApp('/');
    expect(await screen.findByTestId('series-card')).toHaveTextContent(label);
  });

  it('"Continuar leitura" of a book series opens the reader route of that book', async () => {
    fakeApi.on(
      'GET',
      '/api/v1/series/serie-1',
      makeSeriesDetail({ chapters: [book(1), book(2)], continue: { item_id: 'bk-2', locator: 3 } }),
    );
    renderApp('/serie/serie-1');
    expect(await screen.findByTestId('series-start')).toHaveAttribute(
      'href',
      '/ler/bk-2?serie=serie-1',
    );
  });

  it('the library shows a book-only series card and links to it', async () => {
    fakeApi.on('GET', '/api/v1/series', {
      items: [makeSeries({ id: 'serie-9', title: 'Saga', chapter_count: 2, has_cover: false })],
      limit: 30,
      offset: 0,
      has_more: false,
    });
    renderApp('/');
    const card = await screen.findByTestId('series-card');
    expect(card).toHaveAttribute('href', '/serie/serie-9');
    expect(card).toHaveTextContent('Saga');
  });

  it('"Continuar lendo" sends a book to the reader route with ?serie=', async () => {
    fakeApi.on('GET', '/api/v1/progress/continue', {
      items: [
        {
          item: makeItem({ id: 'bk-2', type: 'book', title: 'Livro 2', page_count: null }),
          series_id: 'serie-1',
          series_title: 'Saga',
          locator: 12500,
          percent: 40,
          finished: false,
          updated_at: 'x',
        },
      ],
    });
    renderApp('/');
    const card = await screen.findByTestId('continue-card');
    expect(card).toHaveAttribute('href', '/ler/bk-2?serie=serie-1');
    expect(card).toHaveTextContent('40%');
  });
});
