import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSession } from '../../../shared/session';
import { UpdateNotice } from '../../../shared/system';
import { EnrichControl } from './EnrichControl';
import { useContinueReading } from '../hooks/useContinueReading';
import { useLibrary } from '../hooks/useLibrary';
import { ContinueReading } from './ContinueReading';
import { SeriesCard } from './SeriesCard';
import '../library.css';

export function LibraryPage() {
  const library = useLibrary();
  const continueEntries = useContinueReading();
  const { user } = useSession();
  // In-memory counter: covers are refetched (querystring) once the enrichment finishes.
  const [coverVersion, setCoverVersion] = useState(0);
  const { retry } = library;
  const onEnrichFinished = useCallback(() => {
    setCoverVersion((value) => value + 1);
    retry();
  }, [retry]);

  return (
    <main className="library" data-testid="library-page">
      <header className="library__header">
        <h1 className="library__title">Biblioteca</h1>
        <Link className="btn" to="/ajustes" data-testid="open-settings">
          Ajustes
        </Link>
      </header>

      <UpdateNotice />

      <div className="library__filters">
        <input
          className="input"
          type="search"
          role="searchbox"
          aria-label="Buscar na biblioteca"
          placeholder="Buscar por título"
          maxLength={100}
          autoComplete="off"
          autoCapitalize="none"
          enterKeyHint="search"
          data-testid="library-search"
          value={library.query}
          onChange={(event) => library.setQuery(event.target.value)}
        />
      </div>

      {user?.role === 'admin' && <EnrichControl onFinished={onEnrichFinished} />}

      {!library.filtering && <ContinueReading entries={continueEntries} />}

      {library.status === 'loading' && (
        <div className="library__state" role="status" data-testid="library-loading">
          <div className="spinner" />
          <span className="muted">Carregando biblioteca…</span>
        </div>
      )}

      {library.status === 'error' && (
        <div className="library__state" role="alert" data-testid="library-error">
          <p>Não foi possível carregar a biblioteca.</p>
          <button type="button" className="btn" onClick={library.retry}>
            Tentar novamente
          </button>
        </div>
      )}

      {library.status === 'ready' && library.items.length === 0 && (
        <div className="library__state" data-testid="library-empty">
          {library.filtering ? (
            <p>Nenhuma série encontrada para esta busca.</p>
          ) : (
            <>
              <p>Sua biblioteca está vazia.</p>
              <p className="muted">
                O administrador precisa executar o scan da biblioteca no servidor para que os
                títulos apareçam aqui.
              </p>
            </>
          )}
        </div>
      )}

      {library.status === 'ready' && library.items.length > 0 && (
        <>
          <ul className="grid" data-testid="library-grid">
            {library.items.map((series) => (
              <li key={series.id}>
                <SeriesCard series={series} coverVersion={coverVersion} />
              </li>
            ))}
          </ul>
          {library.moreFailed && (
            <p className="alert alert--error" role="alert">
              Não foi possível carregar mais séries.
            </p>
          )}
          {library.hasMore && (
            <button
              type="button"
              className="btn library__more"
              data-testid="library-load-more"
              disabled={library.loadingMore}
              onClick={() => void library.loadMore()}
            >
              {library.loadingMore ? 'Carregando…' : 'Carregar mais'}
            </button>
          )}
        </>
      )}
    </main>
  );
}
