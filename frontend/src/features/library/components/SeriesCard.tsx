import { Link } from 'react-router-dom';
import { seriesPath } from '../../../shared/items';
import { seriesCountLabel, seriesCoverUrl, type SeriesSummary } from '../../../shared/series';
import { Cover } from '../../../shared/ui';

export function SeriesCard({
  series,
  coverVersion = 0,
}: {
  series: SeriesSummary;
  /** In-memory cache-busting counter (bumped after "Atualizar metadados"). */
  coverVersion?: number;
}) {
  const total = Math.max(0, series.chapter_count);
  const read = Math.min(total, Math.max(0, series.progress.read_chapters));
  return (
    <Link className="card" to={seriesPath(series.id)} data-testid="series-card">
      <Cover
        src={series.has_cover ? seriesCoverUrl(series.id, coverVersion) : null}
        title={series.title}
      />
      <span className="card__title">{series.title}</span>
      <span className="card__meta">{seriesCountLabel(total, series.kind)}</span>
      {total > 0 && (
        <>
          <progress
            className="meter"
            max={total}
            value={read}
            aria-label={`Capítulos lidos de ${series.title}`}
            data-testid="series-progress"
          />
          <span className="card__meta">
            {read} de {total} lidos
          </span>
        </>
      )}
    </Link>
  );
}
