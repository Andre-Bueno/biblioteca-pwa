import { useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { BookInfo, Item, ItemState } from '../../../shared/items';
import { usePreferences } from '../../../shared/preferences';
import '../../../shared/ui';
import { useEpubData } from '../hooks/useEpubData';
import { useEpubReader } from '../hooks/useEpubReader';
import { EpubControls } from './EpubControls';
import { EpubEnd } from './EpubEnd';
import { EpubStrip } from './EpubStrip';
import { SettingsDrawer } from './SettingsDrawer';
import { TocDrawer } from './TocDrawer';
import '../epub.css';

function Reader({
  item,
  book,
  savedLocator,
}: {
  item: Item;
  book: BookInfo;
  savedLocator: number | null;
}) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const reader = useEpubReader({ frameRef, item, book, savedLocator });
  return (
    <div className="epub" data-testid="epub-reader">
      {/*
        The book lives ONLY here: the server sends a sanitized, complete HTML document and the
        sandbox has no allow-scripts / allow-popups / allow-forms / allow-top-navigation.
        allow-same-origin is what lets the app read the scroll position and clicks.
      */}
      {reader.vertical ? (
        <EpubStrip reader={reader} />
      ) : (
        <iframe
          key={reader.frameKey}
          ref={frameRef}
          className="epub-frame"
          title={`Livro ${book.title || item.title}, capítulo ${reader.chapter + 1} de ${reader.count}`}
          src={reader.src}
          sandbox="allow-same-origin"
          referrerPolicy="no-referrer"
          onLoad={reader.onFrameLoad}
          data-testid="epub-frame"
        />
      )}
      {reader.loading && (
        <div className="epub-loading" role="status" data-testid="chapter-loading">
          <div className="spinner" />
          <span className="muted">Carregando capítulo…</span>
        </div>
      )}
      {reader.frameFailed && (
        <div className="epub-failed" role="alert" data-testid="chapter-error">
          <p>Não foi possível carregar este capítulo.</p>
          <button type="button" className="btn" data-testid="chapter-retry" onClick={reader.retry}>
            Tentar novamente
          </button>
        </div>
      )}
      {reader.saveStatus === 'error' && (
        <p className="epub-toast" role="status" data-testid="save-warning">
          Não foi possível salvar o progresso. Tentando novamente…
        </p>
      )}
      {!reader.controlsVisible && (
        <button
          type="button"
          className="btn epub-reveal"
          aria-label="Mostrar controles"
          data-testid="show-controls"
          onClick={reader.toggleControls}
        >
          ☰
        </button>
      )}
      {!reader.controlsVisible && (
        <div className="epub-pill" aria-hidden="true" data-testid="epub-pill">
          {reader.chapter + 1}/{reader.count} · {reader.percent}%
        </div>
      )}
      {reader.atEnd && <EpubEnd reader={reader} />}
      {reader.controlsVisible && <EpubControls reader={reader} />}
      {reader.panel === 'toc' && <TocDrawer reader={reader} />}
      {reader.panel === 'settings' && <SettingsDrawer reader={reader} />}
    </div>
  );
}

function Message({ children }: { children: ReactNode }) {
  return (
    <main className="epub-message" data-testid="reader-message">
      {children}
      <Link className="btn" to="/">
        Voltar para a biblioteca
      </Link>
    </main>
  );
}

interface EpubReaderPageProps {
  /** The item, loaded by the reader route (which picked this reader from its type). */
  itemState: ItemState;
  retryItem: () => void;
}

/** Route screen for a book (`/ler/:itemId` when the item type is `book`). */
export function EpubReaderPage({ itemState, retryItem }: EpubReaderPageProps) {
  const { data, retry } = useEpubData(itemState, retryItem);
  // The first src already uses the saved theme and size; the reading direction picks the mode.
  const { loaded, preferences } = usePreferences();
  const vertical = preferences.reading_direction === 'vertical';

  if (data.status === 'loading' || !loaded) {
    return (
      <div className="splash" role="status" aria-label="Carregando" data-testid="reader-loading">
        <div className="spinner" />
      </div>
    );
  }
  if (data.status === 'notfound') return <Message>Livro não encontrado.</Message>;
  if (data.status === 'error') {
    return (
      <Message>
        Não foi possível abrir este livro.
        <button type="button" className="btn" onClick={retry}>
          Tentar novamente
        </button>
      </Message>
    );
  }
  if (data.book.chapters.length === 0)
    return <Message>Este livro não tem capítulos para ler.</Message>;
  return (
    <Reader
      key={`${data.item.id}:${vertical ? 'v' : 'p'}`}
      item={data.item}
      book={data.book}
      savedLocator={data.savedLocator}
    />
  );
}
