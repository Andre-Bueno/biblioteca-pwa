import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../src/shared/api-client/errors';
import { fakeApi, makeItem, makeSeriesDetail, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

function setup(route: string, opts: { seriesFails?: boolean; itemSeriesId?: string } = {}) {
  signedIn();
  for (const id of ['ch-1', 'ch-2', 'ch-3']) {
    fakeApi.on(
      'GET',
      `/api/v1/items/${id}`,
      makeItem({
        id,
        title: `Capitulo - ${id.slice(3)}`,
        page_count: 3,
        series_id: opts.itemSeriesId,
      }),
    );
    fakeApi.on('GET', `/api/v1/progress/${id}`, () => {
      throw new ApiError(404, 'none');
    });
    fakeApi.on('PUT', `/api/v1/progress/${id}`, ({ body }) => ({ ...(body as object) }));
  }
  if (opts.seriesFails) {
    fakeApi.on('GET', '/api/v1/series/serie-1', () => {
      throw new ApiError(500, 'down');
    });
  } else {
    fakeApi.on('GET', '/api/v1/series/serie-1', makeSeriesDetail());
  }
  renderApp(route);
  return screen.findByTestId('reader');
}

const goToLastPage = () => fireEvent.keyDown(window, { key: 'End' });

describe('reader inside a series', () => {
  beforeEach(() => fakeApi.reset());

  it('does not offer chapter navigation before the last page', async () => {
    await setup('/ler/ch-2?serie=serie-1');
    await waitFor(() => expect(fakeApi.callsTo('GET', '/api/v1/series/serie-1')).toHaveLength(1));
    expect(screen.queryByTestId('chapter-end')).not.toBeInTheDocument();
  });

  it('at the end of the chapter offers next and previous chapter in series order', async () => {
    await setup('/ler/ch-2?serie=serie-1');
    await screen.findByTestId('reader-back');
    goToLastPage();
    const next = await screen.findByTestId('next-chapter');
    expect(next).toHaveAttribute('href', '/ler/ch-3?serie=serie-1');
    expect(screen.getByTestId('previous-chapter')).toHaveAttribute(
      'href',
      '/ler/ch-1?serie=serie-1',
    );
  });

  it('following "Próximo capítulo" opens the next chapter without reloading the series', async () => {
    await setup('/ler/ch-2?serie=serie-1');
    await screen.findByTestId('reader-back');
    goToLastPage();
    await userEvent.setup().click(await screen.findByTestId('next-chapter'));
    await waitFor(() => expect(screen.getByTestId('page-indicator')).toHaveTextContent('1 / 3'));
    expect(fakeApi.callsTo('GET', '/api/v1/items/ch-3')).toHaveLength(1);
    expect(fakeApi.callsTo('GET', '/api/v1/series/serie-1')).toHaveLength(1);
    goToLastPage();
    // last chapter: no next, a friendly note and the previous one
    expect(await screen.findByTestId('series-finished')).toBeInTheDocument();
    expect(screen.queryByTestId('next-chapter')).not.toBeInTheDocument();
    expect(screen.getByTestId('previous-chapter')).toHaveAttribute(
      'href',
      '/ler/ch-2?serie=serie-1',
    );
  });

  it('the first chapter has no "anterior"', async () => {
    await setup('/ler/ch-1?serie=serie-1');
    await screen.findByTestId('reader-back');
    goToLastPage();
    expect(await screen.findByTestId('next-chapter')).toBeInTheDocument();
    expect(screen.queryByTestId('previous-chapter')).not.toBeInTheDocument();
  });

  it('back goes to the series page when the chapter came from it', async () => {
    await setup('/ler/ch-2?serie=serie-1');
    const back = await screen.findByTestId('reader-back');
    expect(back).toHaveAttribute('href', '/serie/serie-1');
    expect(back).toHaveAttribute('aria-label', 'Voltar para a série');
  });

  it('uses the series_id of the item when there is no ?serie=', async () => {
    await setup('/ler/ch-2', { itemSeriesId: 'serie-1' });
    expect(await screen.findByTestId('reader-back')).toHaveAttribute('href', '/serie/serie-1');
  });

  it('without a series the reader behaves as before (back to the library, no chapter nav)', async () => {
    await setup('/ler/ch-2');
    expect(await screen.findByTestId('reader-back')).toHaveAttribute('href', '/');
    goToLastPage();
    expect(screen.queryByTestId('chapter-end')).not.toBeInTheDocument();
  });

  it('keeps reading when the series cannot be loaded (no chapter nav)', async () => {
    await setup('/ler/ch-2?serie=serie-1', { seriesFails: true });
    await screen.findByTestId('reader-back');
    goToLastPage();
    await waitFor(() => expect(fakeApi.callsTo('GET', '/api/v1/series/serie-1')).toHaveLength(1));
    expect(screen.getByTestId('page-indicator')).toHaveTextContent('3 / 3');
    expect(screen.queryByTestId('chapter-end')).not.toBeInTheDocument();
  });
});
