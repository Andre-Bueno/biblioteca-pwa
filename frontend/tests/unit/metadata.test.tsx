import { readFileSync } from 'node:fs';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Cover } from '../../src/shared/ui';
import {
  USER,
  apiError,
  fakeApi,
  makeSeries,
  makeSeriesDetail,
  rateLimited,
  signedIn,
} from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const SERIES = '/api/v1/series/serie-1';
const META = `${SERIES}/metadata`;
const CANDIDATES = `${META}/candidates`;

const candidate = (overrides: Record<string, unknown> = {}) => ({
  provider: 'mangadex',
  external_id: 'abc',
  title: 'Serie Um (oficial)',
  year: 2019,
  description: 'Trecho da descrição.',
  cover_available: true,
  url: 'https://mangadex.org/title/abc',
  ...overrides,
});

function asAdmin() {
  fakeApi.on('GET', '/api/v1/auth/me', { ...USER, role: 'admin' });
}

function open(detail: object = makeSeriesDetail()) {
  fakeApi.on('GET', SERIES, detail);
  renderApp('/serie/serie-1');
}

async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByTestId('meta-toggle'));
}

describe('series description', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it('pt-br description: no badge, short text has no toggle', async () => {
    open(makeSeriesDetail({ description: 'Curta.', description_lang: 'pt-br' }));
    expect(await screen.findByTestId('series-description')).toHaveTextContent('Curta.');
    expect(screen.queryByTestId('description-lang')).not.toBeInTheDocument();
    expect(screen.queryByTestId('description-toggle')).not.toBeInTheDocument();
  });

  it('english and pt-PT descriptions get a badge', async () => {
    open(makeSeriesDetail({ description: 'A story.', description_lang: 'en' }));
    expect(await screen.findByTestId('description-lang')).toHaveTextContent('em inglês');
    cleanup();
    open(makeSeriesDetail({ description: 'Uma história.', description_lang: 'pt' }));
    expect(await screen.findByTestId('description-lang')).toHaveTextContent(
      'em português de Portugal',
    );
  });

  it('no description: no section', async () => {
    open();
    await screen.findByTestId('series-title');
    expect(screen.queryByTestId('series-description')).not.toBeInTheDocument();
  });

  it('long description is collapsed with "Ler mais" / "Ler menos"', async () => {
    open(makeSeriesDetail({ description: 'palavra '.repeat(80), description_lang: 'pt-br' }));
    const text = await screen.findByTestId('series-description');
    expect(text).toHaveAttribute('data-collapsed', 'true');
    const toggle = screen.getByTestId('description-toggle');
    expect(toggle).toHaveTextContent('Ler mais');
    await userEvent.setup().click(toggle);
    expect(text).toHaveAttribute('data-collapsed', 'false');
    expect(toggle).toHaveTextContent('Ler menos');
  });

  it('hostile HTML in title and description stays plain text', async () => {
    const hostile = '<img src=x onerror=alert(1)><script>alert(2)</script>';
    open(makeSeriesDetail({ title: hostile, description: hostile, description_lang: 'pt-br' }));
    const box = await screen.findByTestId('series-description');
    expect(box.textContent).toBe(hostile);
    expect(screen.getByTestId('series-title').textContent).toBe(hostile);
    expect(document.querySelector('main script, main [onerror]')).toBeNull();
  });

  it('only https sources become links', async () => {
    open(makeSeriesDetail({ source: { name: 'AniList', url: 'javascript:alert(1)' } }));
    const source = await screen.findByTestId('series-source');
    expect(source.querySelector('a')).toBeNull();
  });
});

describe('admin metadata panel', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it('is invisible for a regular user and the candidates API is never called', async () => {
    open();
    await screen.findByTestId('series-title');
    expect(screen.queryByTestId('meta-panel')).not.toBeInTheDocument();
    expect(fakeApi.callsTo('GET', CANDIDATES)).toHaveLength(0);
  });

  it('is collapsed by default, shows the state, and does not search on its own', async () => {
    asAdmin();
    open(makeSeriesDetail({ metadata_state: 'matched' }));
    expect(await screen.findByTestId('metadata-state')).toHaveTextContent(
      'Correspondência automática',
    );
    expect(screen.queryByTestId('meta-body')).not.toBeInTheDocument();
    const user = userEvent.setup();
    await openPanel(user);
    expect(screen.getByTestId('meta-query')).toHaveValue('Serie Um');
    expect(fakeApi.callsTo('GET', CANDIDATES)).toHaveLength(0);
  });

  it('lists candidates and "Usar este" reloads the detail and busts the cover cache', async () => {
    asAdmin();
    let selected = false;
    fakeApi.on('GET', CANDIDATES, { items: [candidate()] });
    fakeApi.on('POST', `${META}/select`, () => {
      selected = true;
      return undefined; // 204
    });
    open();
    fakeApi.on('GET', SERIES, () =>
      makeSeriesDetail(
        selected
          ? {
              description: 'Nova descrição.',
              description_lang: 'pt-br',
              metadata_state: 'matched',
              source: { name: 'MangaDex', url: 'https://mangadex.org/title/abc' },
            }
          : {},
      ),
    );
    const user = userEvent.setup();
    await openPanel(user);
    expect(screen.getByTestId('cover-img')).toHaveAttribute('src', '/api/v1/series/serie-1/cover');
    await user.click(screen.getByTestId('meta-search'));
    const item = await screen.findByTestId('candidate');
    expect(item).toHaveTextContent('Serie Um (oficial)');
    expect(item).toHaveTextContent('2019');
    expect(item).toHaveTextContent('Trecho da descrição.');
    await user.click(screen.getByTestId('candidate-use'));
    expect(await screen.findByTestId('series-description')).toHaveTextContent('Nova descrição.');
    expect(fakeApi.callsTo('POST', `${META}/select`)[0]!.body).toEqual({
      provider: 'mangadex',
      external_id: 'abc',
    });
    expect(screen.getByTestId('meta-feedback')).toHaveTextContent('Metadados aplicados.');
    expect(screen.getByTestId('metadata-state')).toHaveTextContent('Correspondência automática');
    expect(screen.getByTestId('cover-img')).toHaveAttribute(
      'src',
      '/api/v1/series/serie-1/cover?v=1',
    );
  });

  it('handles an updated detail returned by select (200) too', async () => {
    asAdmin();
    fakeApi.on('GET', CANDIDATES, { items: [candidate()] });
    fakeApi.on('POST', `${META}/select`, makeSeriesDetail({ metadata_state: 'matched' }));
    open();
    const user = userEvent.setup();
    await openPanel(user);
    await user.click(screen.getByTestId('meta-search'));
    await user.click(await screen.findByTestId('candidate-use'));
    await waitFor(() => expect(fakeApi.callsTo('GET', SERIES).length).toBeGreaterThan(1));
  });

  it('shows empty and error states', async () => {
    asAdmin();
    fakeApi.on('GET', CANDIDATES, { items: [] });
    open();
    const user = userEvent.setup();
    await openPanel(user);
    await user.click(screen.getByTestId('meta-search'));
    expect(await screen.findByTestId('candidates-empty')).toBeInTheDocument();
    fakeApi.on('GET', CANDIDATES, apiError(500));
    await user.click(screen.getByTestId('meta-search'));
    const error = await screen.findByTestId('candidates-error');
    expect(error).not.toHaveTextContent(/500|ApiError|stack/i);
  });

  it('429 shows a friendly notice with the wait and blocks the search button', async () => {
    asAdmin();
    fakeApi.on('GET', CANDIDATES, rateLimited(30));
    open();
    const user = userEvent.setup();
    await openPanel(user);
    await user.click(screen.getByTestId('meta-search'));
    expect(await screen.findByTestId('candidates-rate-limit')).toHaveTextContent('30 s');
    expect(screen.getByTestId('meta-search')).toBeDisabled();
    expect(fakeApi.callsTo('GET', CANDIDATES)).toHaveLength(1);
  });

  it('a failed select shows a generic error', async () => {
    asAdmin();
    fakeApi.on('GET', CANDIDATES, { items: [candidate()] });
    fakeApi.on('POST', `${META}/select`, apiError(502));
    open();
    const user = userEvent.setup();
    await openPanel(user);
    await user.click(screen.getByTestId('meta-search'));
    await user.click(await screen.findByTestId('candidate-use'));
    const feedback = await screen.findByTestId('meta-feedback');
    expect(feedback).toHaveTextContent('Não foi possível aplicar');
    expect(feedback).not.toHaveTextContent('502');
  });

  it('manual edit enforces limits with counters and saves title + description', async () => {
    asAdmin();
    fakeApi.on('PUT', META, undefined);
    open(makeSeriesDetail({ description: 'Antiga.' }));
    const user = userEvent.setup();
    await openPanel(user);
    expect(screen.getByTestId('meta-title-count')).toHaveTextContent('8/200');
    expect(screen.getByTestId('meta-title')).toHaveAttribute('maxlength', '200');
    expect(screen.getByTestId('meta-description')).toHaveAttribute('maxlength', '4000');
    const title = screen.getByTestId('meta-title');
    await user.clear(title);
    expect(screen.getByTestId('meta-save')).toBeDisabled();
    await user.type(title, 'Novo');
    const description = screen.getByTestId('meta-description');
    await user.clear(description);
    await user.type(description, 'Texto novo');
    expect(screen.getByTestId('meta-description-count')).toHaveTextContent('10/4000');
    await user.click(screen.getByTestId('meta-save'));
    expect(await screen.findByText('Texto salvo.')).toBeInTheDocument();
    expect(fakeApi.callsTo('PUT', META)[0]!.body).toEqual({
      title: 'Novo',
      description: 'Texto novo',
    });
  });

  it('removal asks for confirmation; cancel does nothing, confirm sends DELETE', async () => {
    asAdmin();
    fakeApi.on('DELETE', META, undefined);
    open();
    const user = userEvent.setup();
    await openPanel(user);
    await user.click(screen.getByTestId('meta-remove'));
    await user.click(screen.getByTestId('meta-remove-cancel'));
    expect(fakeApi.callsTo('DELETE', META)).toHaveLength(0);
    await user.click(screen.getByTestId('meta-remove'));
    await user.click(screen.getByTestId('meta-remove-confirm'));
    expect(await screen.findByText('Metadados removidos.')).toBeInTheDocument();
    expect(fakeApi.callsTo('DELETE', META)).toHaveLength(1);
  });

  it('candidate text with HTML is rendered as text and unsafe links are dropped', async () => {
    asAdmin();
    const hostile = '<img src=x onerror=alert(1)>';
    fakeApi.on('GET', CANDIDATES, {
      items: [candidate({ title: hostile, description: hostile, url: 'javascript:alert(1)' })],
    });
    open();
    const user = userEvent.setup();
    await openPanel(user);
    await user.click(screen.getByTestId('meta-search'));
    const item = await screen.findByTestId('candidate');
    expect(item.querySelector('img, a')).toBeNull();
    expect(item).toHaveTextContent(hostile);
  });
});

describe('library "Atualizar metadados"', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
    fakeApi.on('GET', '/api/v1/series', {
      items: [makeSeries()],
      limit: 30,
      offset: 0,
      has_more: false,
    });
  });
  afterEach(() => vi.useRealTimers());

  it('is not shown to a regular user', async () => {
    renderApp('/');
    await screen.findByTestId('library-grid');
    expect(screen.queryByTestId('enrich-button')).not.toBeInTheDocument();
  });

  it('polls every 2 s while running and stops when finished', async () => {
    asAdmin();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let polls = 0;
    fakeApi.on('POST', '/api/v1/library/enrich', undefined);
    fakeApi.on('GET', '/api/v1/library/enrich/status', () => {
      polls += 1;
      return polls < 2
        ? { state: 'running', matched: 1, not_found: 0, skipped: 0, errors: 0 }
        : { state: 'finished', matched: 5, not_found: 2, skipped: 0, errors: 0 };
    });
    renderApp('/');
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const button = await screen.findByTestId('enrich-button');
    await user.click(button);
    expect(button).toBeDisabled();
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await screen.findByTestId('enrich-status')).toHaveTextContent('1 encontrado, 0 sem');
    await act(() => vi.advanceTimersByTimeAsync(2000));
    await waitFor(() =>
      expect(screen.getByTestId('enrich-status')).toHaveTextContent(
        'Concluído: 5 encontrados, 2 sem correspondência',
      ),
    );
    expect(screen.getByTestId('enrich-button')).toBeEnabled();
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(polls).toBe(2);
  });

  it('409 (already running) just follows the status', async () => {
    asAdmin();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fakeApi.on('POST', '/api/v1/library/enrich', apiError(409));
    fakeApi.on('GET', '/api/v1/library/enrich/status', {
      state: 'finished',
      matched: 3,
      not_found: 1,
      skipped: 0,
      errors: 0,
    });
    renderApp('/');
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(await screen.findByTestId('enrich-button'));
    await act(() => vi.advanceTimersByTimeAsync(2000));
    await waitFor(() =>
      expect(screen.getByTestId('enrich-status')).toHaveTextContent('3 encontrados, 1 sem'),
    );
  });

  it('stops polling when leaving the screen', async () => {
    asAdmin();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fakeApi.on('POST', '/api/v1/library/enrich', undefined);
    fakeApi.on('GET', '/api/v1/library/enrich/status', {
      state: 'running',
      matched: 0,
      not_found: 0,
      skipped: 0,
      errors: 0,
    });
    const view = renderApp('/');
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(await screen.findByTestId('enrich-button'));
    await act(() => vi.advanceTimersByTimeAsync(2000));
    const before = fakeApi.callsTo('GET', '/api/v1/library/enrich/status').length;
    expect(before).toBeGreaterThan(0);
    view.unmount();
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(fakeApi.callsTo('GET', '/api/v1/library/enrich/status')).toHaveLength(before);
  });

  it('shows a generic message when the start fails', async () => {
    asAdmin();
    fakeApi.on('POST', '/api/v1/library/enrich', apiError(500));
    renderApp('/');
    await userEvent.setup().click(await screen.findByTestId('enrich-button'));
    const message = await screen.findByTestId('enrich-message');
    expect(message).not.toHaveTextContent('500');
    expect(screen.getByTestId('enrich-button')).toBeEnabled();
  });
});

describe('description origin and attribution', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });
  const base = { description: 'Texto.', description_lang: 'pt-br' };

  it('translated: badge, "original em inglês" and linked https source', async () => {
    open(
      makeSeriesDetail({
        ...base,
        description_origin: 'translated',
        description_source: { name: 'AniList', url: 'https://anilist.co/manga/1' },
      }),
    );
    const origin = await screen.findByTestId('description-origin');
    expect(origin).toHaveTextContent('tradução automática');
    expect(origin).toHaveTextContent('a partir do original em inglês');
    const link = screen.getByTestId('description-source').querySelector('a')!;
    expect(link).toHaveTextContent('AniList');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('target', '_blank');
    expect(screen.queryByTestId('description-license')).not.toBeInTheDocument();
  });

  it('manual: "editada manualmente"', async () => {
    open(makeSeriesDetail({ ...base, description_origin: 'manual' }));
    expect(await screen.findByTestId('description-origin')).toHaveTextContent(
      'editada manualmente',
    );
    expect(screen.queryByTestId('description-source')).not.toBeInTheDocument();
  });

  it('Wikipédia shows CC BY-SA as text', async () => {
    open(
      makeSeriesDetail({
        ...base,
        description_origin: 'source',
        description_source: { name: 'Wikipédia', url: 'https://pt.wikipedia.org/wiki/X' },
      }),
    );
    const source = await screen.findByTestId('description-source');
    expect(source).toHaveTextContent('Descrição: Wikipédia');
    expect(screen.getByTestId('description-license')).toHaveTextContent('CC BY-SA');
    expect(screen.queryByTestId('description-origin')).not.toBeInTheDocument();
  });

  it('keeps the "em inglês" badge when the language is en', async () => {
    open(
      makeSeriesDetail({
        description: 'A story.',
        description_lang: 'en',
        description_origin: 'source',
        description_source: { name: 'MangaDex', url: null },
      }),
    );
    expect(await screen.findByTestId('description-lang')).toHaveTextContent('em inglês');
  });

  it('absent fields behave as before (no credits)', async () => {
    open(makeSeriesDetail(base));
    await screen.findByTestId('series-description');
    expect(screen.queryByTestId('description-credits')).not.toBeInTheDocument();
  });

  it.each(['http://x.org/a', 'javascript:alert(1)', 'data:text/html,hi', null])(
    'non-https url %s is not a link and hostile name stays text',
    async (url) => {
      const name = '<img src=x onerror=alert(1)>';
      open(makeSeriesDetail({ ...base, description_source: { name, url } }));
      const source = await screen.findByTestId('description-source');
      expect(source.querySelector('a, img')).toBeNull();
      expect(source).toHaveTextContent(name);
    },
  );
});

describe('candidate labels', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it('shows friendly provider names and "só descrição" without cover', async () => {
    asAdmin();
    fakeApi.on('GET', CANDIDATES, {
      items: [
        candidate({ provider: 'mangadex', external_id: '1', url: null }),
        candidate({ provider: 'anilist', external_id: '2', url: null }),
        candidate({
          provider: 'wikipedia',
          external_id: '3',
          url: null,
          cover_available: false,
        }),
        candidate({ provider: 'googlebooks', external_id: '4', url: null }),
      ],
    });
    open();
    const user = userEvent.setup();
    await openPanel(user);
    await user.click(screen.getByTestId('meta-search'));
    const items = await screen.findAllByTestId('candidate');
    expect(
      items.map((el) => /MangaDex|AniList|Wikipédia|Google Livros/.exec(el.textContent)?.[0]),
    ).toEqual(['MangaDex', 'AniList', 'Wikipédia', 'Google Livros']);
    expect(screen.getAllByTestId('candidate-text-only')).toHaveLength(1);
    expect(items[2]).toHaveTextContent('só descrição');
  });
});

describe('library cover cache-busting after enrich', () => {
  afterEach(() => vi.useRealTimers());

  it('card covers get ?v=1 when the enrichment finishes', async () => {
    fakeApi.reset();
    signedIn();
    asAdmin();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fakeApi.on('GET', '/api/v1/series', {
      items: [makeSeries()],
      limit: 30,
      offset: 0,
      has_more: false,
    });
    fakeApi.on('POST', '/api/v1/library/enrich', undefined);
    fakeApi.on('GET', '/api/v1/library/enrich/status', {
      state: 'finished',
      matched: 1,
      not_found: 0,
      skipped: 0,
      errors: 0,
    });
    renderApp('/');
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    expect(await screen.findByTestId('cover-img')).toHaveAttribute(
      'src',
      '/api/v1/series/serie-1/cover',
    );
    await user.click(screen.getByTestId('enrich-button'));
    await act(() => vi.advanceTimersByTimeAsync(2000));
    await waitFor(() =>
      expect(screen.getByTestId('cover-img')).toHaveAttribute(
        'src',
        '/api/v1/series/serie-1/cover?v=1',
      ),
    );
  });
});

describe('Cover with a very tall image', () => {
  it('keeps the fixed-ratio frame and the cover image class (cropped from the top by CSS)', () => {
    render(<Cover src="/api/v1/series/x/cover" title="Webtoon" />);
    const img = screen.getByTestId('cover-img');
    expect(img).toHaveClass('cover__img');
    expect(img.closest('.cover')).not.toBeNull();
    expect(img).toHaveAttribute('src', '/api/v1/series/x/cover');
  });

  it('css crops from the top with a fixed 2/3 ratio', () => {
    const css = readFileSync('src/shared/ui/ui.css', 'utf8');
    expect(css).toMatch(/\.cover\s*{[^}]*aspect-ratio:\s*2\s*\/\s*3/);
    expect(css).toMatch(/\.cover__img\s*{[^}]*object-fit:\s*cover;[^}]*object-position:\s*top/);
  });

  it('falls back to the initial letter without an image', () => {
    render(<Cover src={null} title="webtoon" />);
    expect(screen.getByText('W')).toBeInTheDocument();
  });
});
