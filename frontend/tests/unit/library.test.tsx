import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiError, fakeApi, makeItem, makeSeries, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const page = (items: unknown[], hasMore = false, offset = 0) => ({
  items,
  limit: 30,
  offset,
  has_more: hasMore,
});

const seriesCalls = () => fakeApi.callsTo('GET', '/api/v1/series').map((c) => c.path);

describe('library (series)', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it('renders series cards with cover, title, chapter count and read progress', async () => {
    fakeApi.on(
      'GET',
      '/api/v1/series',
      page([
        makeSeries({
          id: 'a',
          title: 'Alpha',
          chapter_count: 200,
          progress: { read_chapters: 50, last_item_id: 'x' },
        }),
        makeSeries({ id: 'b', title: 'Beta', has_cover: false, chapter_count: 1 }),
      ]),
    );
    renderApp('/');
    const cards = await screen.findAllByTestId('series-card');
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute('href', '/serie/a');
    const cover = within(cards[0]!).getByTestId('cover-img');
    expect(cover).toHaveAttribute('src', '/api/v1/series/a/cover');
    expect(cover).toHaveAttribute('loading', 'lazy');
    expect(cards[0]).toHaveTextContent('200 capítulos');
    expect(cards[0]).toHaveTextContent('50 de 200 lidos');
    expect(within(cards[0]!).getByTestId('series-progress')).toHaveAttribute('value', '50');
    expect(within(cards[1]!).queryByTestId('cover-img')).not.toBeInTheDocument();
    expect(cards[1]).toHaveTextContent('1 capítulo');
    expect(cards[1]).not.toHaveTextContent('1 capítulos');
  });

  it('explains that the administrator must run the scan when the library is empty', async () => {
    renderApp('/');
    const empty = await screen.findByTestId('library-empty');
    expect(empty).toHaveTextContent('administrador');
    expect(empty).toHaveTextContent('scan');
  });

  it('shows the loading state, then an error with retry', async () => {
    let attempts = 0;
    fakeApi.on('GET', '/api/v1/series', () => {
      attempts += 1;
      if (attempts === 1) {
        return new Promise((_resolve, reject) => setTimeout(() => reject(new Error('boom')), 150));
      }
      return page([makeSeries({ title: 'Depois' })]);
    });
    renderApp('/');
    expect(await screen.findByTestId('library-loading')).toBeInTheDocument();
    const error = await screen.findByTestId('library-error');
    await userEvent.setup().click(within(error).getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByTestId('series-card')).toBeInTheDocument();
  });

  it('debounces the search into ONE request carrying q', async () => {
    fakeApi.on('GET', '/api/v1/series', page([makeSeries()]));
    renderApp('/');
    await screen.findByTestId('series-card');
    const before = seriesCalls().length;

    await userEvent.setup().type(screen.getByTestId('library-search'), 'omn');
    await waitFor(() => expect(seriesCalls().some((p) => p.includes('q=omn'))).toBe(true));
    const added = seriesCalls().slice(before);
    expect(added).toHaveLength(1);
    expect(added[0]).toContain('q=omn');
  });

  it('a search with no match says so (and does not mention the scan)', async () => {
    fakeApi.on('GET', '/api/v1/series', ({ path }) =>
      path.includes('q=zzz') ? page([]) : page([makeSeries()]),
    );
    renderApp('/');
    await screen.findByTestId('series-card');
    await userEvent.setup().type(screen.getByTestId('library-search'), 'zzz');
    const empty = await screen.findByTestId('library-empty');
    expect(empty).toHaveTextContent('Nenhuma série encontrada');
    expect(empty).not.toHaveTextContent('scan');
  });

  it('a late answer for an old query never overwrites the newer one', async () => {
    fakeApi.on('GET', '/api/v1/series', ({ path }) => {
      if (path.includes('q=abc')) return page([makeSeries({ id: 'new', title: 'Nova' })]);
      if (path.includes('q=ab')) {
        return new Promise((resolve) =>
          setTimeout(() => resolve(page([makeSeries({ id: 'old', title: 'Velha' })])), 700),
        );
      }
      return page([makeSeries()]);
    });
    renderApp('/');
    await screen.findByTestId('series-card');
    const user = userEvent.setup();
    await user.type(screen.getByTestId('library-search'), 'ab');
    await waitFor(() => expect(seriesCalls().some((p) => p.includes('q=ab'))).toBe(true));
    await user.type(screen.getByTestId('library-search'), 'c');
    expect(await screen.findByText('Nova')).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 900));
    expect(screen.queryByText('Velha')).not.toBeInTheDocument();
    expect(screen.getByText('Nova')).toBeInTheDocument();
  });

  it('has no type filter any more', async () => {
    renderApp('/');
    await screen.findByTestId('library-empty');
    expect(screen.queryByTestId('library-type')).not.toBeInTheDocument();
  });

  it('loads more by offset and appends without duplicates', async () => {
    fakeApi.on('GET', '/api/v1/series', ({ path }) =>
      path.includes('offset=2')
        ? page([makeSeries({ id: 'b', title: 'B' }), makeSeries({ id: 'c', title: 'C' })], false, 2)
        : page([makeSeries({ id: 'a', title: 'A' }), makeSeries({ id: 'b', title: 'B' })], true),
    );
    renderApp('/');
    await screen.findAllByTestId('series-card');
    await userEvent.setup().click(screen.getByTestId('library-load-more'));
    await waitFor(() => expect(screen.getAllByTestId('series-card')).toHaveLength(3));
    expect(seriesCalls().at(-1)).toContain('offset=2');
    expect(screen.queryByTestId('library-load-more')).not.toBeInTheDocument();
  });

  it('a failed "load more" keeps the grid and shows a notice', async () => {
    fakeApi.on('GET', '/api/v1/series', ({ path }) => {
      if (path.includes('offset=1')) throw new Error('down');
      return page([makeSeries({ id: 'a' })], true);
    });
    renderApp('/');
    await screen.findByTestId('series-card');
    await userEvent.setup().click(screen.getByTestId('library-load-more'));
    expect(await screen.findByRole('alert')).toHaveTextContent('mais séries');
    expect(screen.getAllByTestId('series-card')).toHaveLength(1);
  });

  it('"continue reading" shows series + chapter and opens the reader in that series', async () => {
    fakeApi.on('GET', '/api/v1/progress/continue', {
      items: [
        {
          item: makeItem({ id: 'z', title: 'Capitulo - 7' }),
          series_id: 's9',
          series_title: 'Omniscient Reader',
          locator: 4,
          percent: 40,
          finished: false,
          updated_at: '2026-02-01T00:00:00Z',
        },
      ],
    });
    renderApp('/');
    const card = await screen.findByTestId('continue-card');
    expect(card).toHaveAttribute('href', '/ler/z?serie=s9');
    expect(card).toHaveTextContent('Omniscient Reader');
    expect(within(card).getByTestId('continue-chapter')).toHaveTextContent('Capitulo - 7');
    expect(within(card).getByTestId('cover-img')).toHaveAttribute('src', '/api/v1/series/s9/cover');
    expect(within(card).getByRole('progressbar')).toHaveAttribute('value', '40');
    expect(card).toHaveTextContent('40%');
  });

  it('keeps working when "continue reading" fails', async () => {
    fakeApi.on('GET', '/api/v1/progress/continue', apiError(500));
    fakeApi.on('GET', '/api/v1/series', page([makeSeries()]));
    renderApp('/');
    expect(await screen.findByTestId('series-card')).toBeInTheDocument();
    expect(screen.queryByTestId('continue-reading')).not.toBeInTheDocument();
  });
});
