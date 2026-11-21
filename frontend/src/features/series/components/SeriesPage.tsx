import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { readerPath } from '../../../shared/items';
import { useSession } from '../../../shared/session';
import {
  safeHttpsUrl,
  seriesCoverUrl,
  useSeriesDetail,
  type SeriesDetail,
} from '../../../shared/series';
import { Cover } from '../../../shared/ui';
import { ChapterList } from './ChapterList';
import { MetadataPanel } from './MetadataPanel';
import { SeriesDescription } from './SeriesDescription';
import '../series.css';

function startTarget(series: SeriesDetail): { to: string; label: string } | null {
  if (series.continue) {
    return { to: readerPath(series.continue.item_id, series.id), label: 'Continuar leitura' };
  }
  const first = series.chapters[0];
  return first ? { to: readerPath(first.id, series.id), label: 'Começar a ler' } : null;
}

interface ContentProps {
  series: SeriesDetail;
  coverVersion: number;
  isAdmin: boolean;
  onMetadataChanged: () => void;
}

function SeriesContent({ series, coverVersion, isAdmin, onMetadataChanged }: ContentProps) {
  const start = startTarget(series);
  const sourceUrl = safeHttpsUrl(series.source?.url);
  return (
    <>
      <div className="series__hero">
        <Cover
          className="series__cover"
          src={series.has_cover ? seriesCoverUrl(series.id, coverVersion) : null}
          title={series.title}
          loading="eager"
        />
        <div className="series__info">
          <h1 className="series__title" data-testid="series-title">
            {series.title}
          </h1>
          <p className="muted" data-testid="series-count">
            {series.chapter_count === 1 ? '1 capítulo' : `${series.chapter_count} capítulos`}
          </p>
          {series.source && (
            <p className="muted" data-testid="series-source">
              Fonte:{' '}
              {sourceUrl ? (
                <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                  {series.source.name}
                </a>
              ) : (
                series.source.name
              )}
            </p>
          )}
          {start && (
            <Link className="btn btn--primary" to={start.to} data-testid="series-start">
              {start.label}
            </Link>
          )}
        </div>
      </div>

      <SeriesDescription series={series} />

      {isAdmin && <MetadataPanel series={series} onChanged={onMetadataChanged} />}

      {series.chapters.length === 0 ? (
        <p className="series__state" data-testid="series-empty">
          Esta série ainda não tem capítulos.
        </p>
      ) : (
        <ChapterList chapters={series.chapters} seriesId={series.id} />
      )}
    </>
  );
}

export function SeriesPage() {
  const { id = '' } = useParams();
  const { state, retry, reload } = useSeriesDetail(id);
  const { user } = useSession();
  // Local counter used only as a querystring so the browser refetches the cover after a change.
  const [coverVersion, setCoverVersion] = useState(0);
  const onMetadataChanged = useCallback(() => {
    setCoverVersion((value) => value + 1);
    reload();
  }, [reload]);

  return (
    <main className="series" data-testid="series-page">
      <header className="series__header">
        <Link className="btn" to="/" data-testid="series-back">
          ‹ Biblioteca
        </Link>
      </header>

      {state.status === 'loading' && (
        <div className="series__state" role="status" data-testid="series-loading">
          <div className="spinner" />
          <span className="muted">Carregando série…</span>
        </div>
      )}
      {state.status === 'notfound' && (
        <div className="series__state" data-testid="series-notfound">
          <p>Série não encontrada.</p>
        </div>
      )}
      {state.status === 'error' && (
        <div className="series__state" role="alert" data-testid="series-error">
          <p>Não foi possível carregar a série.</p>
          <button type="button" className="btn" onClick={retry}>
            Tentar novamente
          </button>
        </div>
      )}
      {state.status === 'ready' && (
        <SeriesContent
          key={state.series.id}
          series={state.series}
          coverVersion={coverVersion}
          isAdmin={user?.role === 'admin'}
          onMetadataChanged={onMetadataChanged}
        />
      )}
    </main>
  );
}
