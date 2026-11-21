import type { ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { Item } from '../../../shared/items';
import { usePreferences } from '../../../shared/preferences';
import '../../../shared/ui';
import { useReaderData } from '../hooks/useReaderData';
import { useReaderNav, type ReaderNav } from '../hooks/useReaderNav';
import { ChapterEnd } from './ChapterEnd';
import { useReaderState } from '../hooks/useReaderState';
import { PagedViewport } from './PagedViewport';
import { ReaderControls } from './ReaderControls';
import { VerticalViewport } from './VerticalViewport';
import '../reader.css';

function Reader({
  item,
  savedLocator,
  nav,
}: {
  item: Item;
  savedLocator: number | null;
  nav: ReaderNav;
}) {
  const reader = useReaderState({ item, savedLocator });
  const atEnd = reader.pageCount > 0 && reader.page >= reader.pageCount - 1;
  return (
    <div className="reader" data-testid="reader" data-mode={reader.mode}>
      {reader.mode === 'vertical' ? (
        <VerticalViewport reader={reader} />
      ) : (
        <PagedViewport reader={reader} />
      )}
      <div
        className={`page-indicator${reader.controlsVisible ? ' page-indicator--raised' : ''}`}
        data-testid="page-indicator"
        aria-live="polite"
        aria-atomic="true"
      >
        {reader.page + 1} / {reader.pageCount}
      </div>
      {!reader.controlsVisible && (
        <button
          type="button"
          className="btn reader-reveal"
          aria-label="Mostrar controles"
          data-testid="show-controls"
          onClick={reader.toggleControls}
        >
          ☰
        </button>
      )}
      {reader.saveStatus === 'error' && (
        <p className="reader-toast" role="status" data-testid="save-warning">
          Não foi possível salvar o progresso. Tentando novamente…
        </p>
      )}
      {atEnd && <ChapterEnd nav={nav} raised={reader.controlsVisible} />}
      {reader.controlsVisible && <ReaderControls reader={reader} nav={nav} />}
    </div>
  );
}

function Message({ children }: { children: ReactNode }) {
  return (
    <main className="reader-message" data-testid="reader-message">
      {children}
      <Link className="btn" to="/">
        Voltar para a biblioteca
      </Link>
    </main>
  );
}

export function MangaReaderPage() {
  const { itemId = '' } = useParams();
  const { data, retry } = useReaderData(itemId);
  const { loaded } = usePreferences(); // the default reading mode comes from the preferences
  const nav = useReaderNav(data.status === 'ready' ? data.item : null);

  if (data.status === 'loading' || !loaded) {
    return (
      <div className="splash" role="status" aria-label="Carregando" data-testid="reader-loading">
        <div className="spinner" />
      </div>
    );
  }
  if (data.status === 'notfound') return <Message>Item não encontrado.</Message>;
  if (data.status === 'error') {
    return (
      <Message>
        Não foi possível abrir este item.
        <button type="button" className="btn" onClick={retry}>
          Tentar novamente
        </button>
      </Message>
    );
  }
  if (data.item.type !== 'manga') {
    return <Message>Este formato ainda não é suportado.</Message>;
  }
  if (!data.item.page_count) return <Message>Este item não tem páginas para ler.</Message>;
  return <Reader key={data.item.id} item={data.item} savedLocator={data.savedLocator} nav={nav} />;
}
