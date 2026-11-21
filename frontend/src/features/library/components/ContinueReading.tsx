import { Link } from 'react-router-dom';
import { coverUrl, readerPath } from '../../../shared/items';
import type { ContinueEntry } from '../../../shared/progress';
import { seriesCoverUrl } from '../../../shared/series';
import { Cover } from '../../../shared/ui';

function percentOf(entry: ContinueEntry): number {
  const value = Number.isFinite(entry.percent) ? entry.percent : 0;
  return Math.min(100, Math.max(0, entry.finished ? 100 : value));
}

export function ContinueReading({ entries }: { entries: ContinueEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <section className="shelf" aria-labelledby="continue-title" data-testid="continue-reading">
      <h2 id="continue-title" className="shelf__title">
        Continuar lendo
      </h2>
      <ul className="shelf__list">
        {entries.map((entry) => {
          const percent = percentOf(entry);
          const seriesId = entry.series_id ?? null;
          const title = entry.series_title ?? entry.item.title;
          const cover = seriesId
            ? seriesCoverUrl(seriesId)
            : entry.item.has_cover
              ? coverUrl(entry.item.id)
              : null;
          return (
            <li key={entry.item.id} className="shelf__item">
              <Link
                className="card card--shelf"
                to={readerPath(entry.item.id, seriesId)}
                data-testid="continue-card"
              >
                <Cover src={cover} title={title} />
                <span className="card__title">{title}</span>
                {entry.series_title && (
                  <span className="card__meta" data-testid="continue-chapter">
                    {entry.item.title}
                  </span>
                )}
                <progress
                  className="meter"
                  max={100}
                  value={percent}
                  aria-label={`Progresso de ${entry.item.title}`}
                />
                <span className="card__meta">
                  {entry.finished ? 'Concluído' : `${Math.round(percent)}%`}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
