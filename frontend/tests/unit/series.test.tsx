import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiError, fakeApi, makeChapter, makeSeriesDetail, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

function open(detail: unknown = makeSeriesDetail()) {
  fakeApi.on('GET', '/api/v1/series/serie-1', detail as object);
  renderApp('/serie/serie-1');
}

describe('series page', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it('shows cover, title, count and a back link to the library', async () => {
    open();
    expect(await screen.findByTestId('series-title')).toHaveTextContent('Serie Um');
    expect(screen.getByTestId('cover-img')).toHaveAttribute('src', '/api/v1/series/serie-1/cover');
    expect(screen.getByTestId('series-count')).toHaveTextContent('3 capítulos');
    expect(screen.getByTestId('series-back')).toHaveAttribute('href', '/');
  });

  it('"Começar a ler" opens the first chapter when there is no continue point', async () => {
    open();
    const start = await screen.findByTestId('series-start');
    expect(start).toHaveTextContent('Começar a ler');
    expect(start).toHaveAttribute('href', '/ler/ch-1?serie=serie-1');
  });

  it('"Continuar leitura" opens the chapter saved in `continue`', async () => {
    open(makeSeriesDetail({ continue: { item_id: 'ch-2', locator: 4 } }));
    const start = await screen.findByTestId('series-start');
    expect(start).toHaveTextContent('Continuar leitura');
    expect(start).toHaveAttribute('href', '/ler/ch-2?serie=serie-1');
  });

  it('lists chapters in the order received with pages and read state', async () => {
    open(
      makeSeriesDetail({
        chapters: [
          makeChapter(1, { progress: { locator: 9, percent: 100, finished: true } }),
          makeChapter(2, { progress: { locator: 3, percent: 40, finished: false } }),
          makeChapter(3, { page_count: 1 }),
        ],
      }),
    );
    const rows = await screen.findAllByTestId('chapter-row');
    expect(rows.map((row) => row.getAttribute('data-status'))).toEqual([
      'done',
      'reading',
      'unread',
    ]);
    expect(rows[0]).toHaveTextContent('Capitulo - 1');
    expect(rows[0]).toHaveTextContent('10 páginas · Concluído');
    expect(rows[1]).toHaveTextContent('Em andamento (40%)');
    expect(within(rows[1]!).getByRole('progressbar')).toHaveAttribute('value', '40');
    expect(rows[2]).toHaveTextContent('1 página · Não lido');
    expect(rows[2]).toHaveAttribute('href', '/ler/ch-3?serie=serie-1');
  });

  describe('long list (200+ chapters)', () => {
    const many = () =>
      makeSeriesDetail({
        chapter_count: 230,
        chapters: Array.from({ length: 230 }, (_, i) => makeChapter(i + 1)),
      });

    it('renders only a window and grows with "mostrar mais"', async () => {
      open(many());
      await screen.findByTestId('chapter-list');
      expect(screen.getAllByTestId('chapter-row')).toHaveLength(50);
      const more = screen.getByTestId('chapters-more');
      expect(more).toHaveTextContent('180 restantes');
      await userEvent.setup().click(more);
      expect(screen.getAllByTestId('chapter-row')).toHaveLength(100);
    });

    it('"ir para o capítulo N" expands the window, scrolls and highlights', async () => {
      const scrollIntoView = vi.fn();
      Element.prototype.scrollIntoView = scrollIntoView;
      open(many());
      await screen.findByTestId('chapter-list');
      const user = userEvent.setup();
      await user.type(screen.getByTestId('goto-input'), '172');
      await user.click(screen.getByTestId('goto-submit'));
      const target = document.getElementById('chapter-ch-172')!;
      expect(target).toBeInTheDocument();
      expect(screen.getAllByTestId('chapter-row')).toHaveLength(200);
      expect(within(target).getByTestId('chapter-row').className).toContain('chapter--highlight');
      expect(scrollIntoView).toHaveBeenCalled();
      // @ts-expect-error restore jsdom's lack of scrollIntoView
      delete Element.prototype.scrollIntoView;
    });

    it('rejects an invalid or unknown chapter number', async () => {
      open(many());
      await screen.findByTestId('chapter-list');
      const user = userEvent.setup();
      await user.type(screen.getByTestId('goto-input'), 'abc');
      await user.click(screen.getByTestId('goto-submit'));
      expect(await screen.findByTestId('goto-error')).toHaveTextContent('válido');
      await user.clear(screen.getByTestId('goto-input'));
      await user.type(screen.getByTestId('goto-input'), '999');
      await user.click(screen.getByTestId('goto-submit'));
      expect(await screen.findByTestId('goto-error')).toHaveTextContent('não encontrado');
    });
  });

  describe('description', () => {
    it('pt-br description has no language badge', async () => {
      open(makeSeriesDetail({ description: 'Uma história.', description_lang: 'pt-br' }));
      expect(await screen.findByTestId('series-description')).toHaveTextContent('Uma história.');
      expect(screen.queryByTestId('description-lang')).not.toBeInTheDocument();
    });

    it('an English description gets a discreet "em inglês" badge', async () => {
      open(makeSeriesDetail({ description: 'A story.', description_lang: 'en' }));
      expect(await screen.findByTestId('description-lang')).toHaveTextContent('em inglês');
    });

    it('renders hostile HTML as plain text', async () => {
      const hostile = '<img src=x onerror=alert(1)><script>alert(2)</script><b>negrito</b>';
      open(makeSeriesDetail({ description: hostile, description_lang: 'pt-br' }));
      const box = await screen.findByTestId('series-description');
      expect(box.textContent).toBe(hostile);
      expect(box.querySelector('img, script, b')).toBeNull();
    });

    it('no description section when there is none', async () => {
      open();
      await screen.findByTestId('series-title');
      expect(screen.queryByTestId('series-description')).not.toBeInTheDocument();
    });
  });

  describe('source', () => {
    it('links to an https source with a safe rel', async () => {
      open(makeSeriesDetail({ source: { name: 'MangaDex', url: 'https://mangadex.org/title/1' } }));
      const link = await within(await screen.findByTestId('series-source')).findByRole('link');
      expect(link).toHaveTextContent('MangaDex');
      expect(link).toHaveAttribute('href', 'https://mangadex.org/title/1');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
      expect(link).toHaveAttribute('target', '_blank');
    });

    it.each(['http://mangadex.org/x', 'javascript:alert(1)', 'data:text/html,hi', 'nope'])(
      'shows the name without a link for %s',
      async (url) => {
        open(makeSeriesDetail({ source: { name: 'MangaDex', url } }));
        const source = await screen.findByTestId('series-source');
        expect(source).toHaveTextContent('Fonte: MangaDex');
        expect(within(source).queryByRole('link')).not.toBeInTheDocument();
      },
    );
  });

  it('shows an empty state for a series without chapters', async () => {
    open(makeSeriesDetail({ chapters: [], chapter_count: 0 }));
    expect(await screen.findByTestId('series-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('series-start')).not.toBeInTheDocument();
  });

  it('shows "não encontrada" for an unknown series (404)', async () => {
    renderApp('/serie/serie-1'); // no route registered: fake api answers 404
    expect(await screen.findByTestId('series-notfound')).toBeInTheDocument();
  });

  it('shows an error with retry for other failures', async () => {
    let attempts = 0;
    fakeApi.on('GET', '/api/v1/series/serie-1', () => {
      attempts += 1;
      if (attempts === 1) apiError(500)();
      return makeSeriesDetail();
    });
    renderApp('/serie/serie-1');
    const error = await screen.findByTestId('series-error');
    await userEvent.setup().click(within(error).getByRole('button', { name: /tentar novamente/i }));
    expect(await screen.findByTestId('series-title')).toBeInTheDocument();
  });
});
