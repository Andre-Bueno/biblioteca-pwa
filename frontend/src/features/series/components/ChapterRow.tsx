import { Link } from 'react-router-dom';
import { readerPath } from '../../../shared/items';
import type { Chapter } from '../../../shared/series';

function percentOf(chapter: Chapter): number {
  const progress = chapter.progress;
  if (!progress) return 0;
  const value = Number.isFinite(progress.percent) ? progress.percent : 0;
  return Math.min(100, Math.max(0, progress.finished ? 100 : value));
}

export function chapterStatus(chapter: Chapter): 'unread' | 'reading' | 'done' {
  if (!chapter.progress) return 'unread';
  return chapter.progress.finished ? 'done' : 'reading';
}

function statusLabel(status: 'unread' | 'reading' | 'done'): string {
  if (status === 'done') return 'Concluído';
  return status === 'reading' ? 'Em andamento' : 'Não lido';
}

interface ChapterRowProps {
  chapter: Chapter;
  seriesId: string;
  highlighted: boolean;
}

export function ChapterRow({ chapter, seriesId, highlighted }: ChapterRowProps) {
  const status = chapterStatus(chapter);
  const percent = percentOf(chapter);
  const pages = chapter.page_count ?? 0;
  return (
    <li id={`chapter-${chapter.id}`} className="chapter-list__item">
      <Link
        className={`chapter${highlighted ? ' chapter--highlight' : ''}`}
        to={readerPath(chapter.id, seriesId)}
        data-testid="chapter-row"
        data-status={status}
      >
        <span className="chapter__title">{chapter.title}</span>
        <span className="chapter__meta">
          {pages === 1 ? '1 página' : `${pages} páginas`} · {statusLabel(status)}
          {status === 'reading' ? ` (${Math.round(percent)}%)` : ''}
        </span>
        {status === 'reading' && (
          <progress
            className="meter"
            max={100}
            value={percent}
            aria-label={`Progresso de ${chapter.title}`}
          />
        )}
      </Link>
    </li>
  );
}
