import { Link } from 'react-router-dom';
import type { ReaderNav } from '../hooks/useReaderNav';

/** Shown on the last page of a chapter that belongs to a series: next / previous chapter. */
export function ChapterEnd({ nav, raised }: { nav: ReaderNav; raised: boolean }) {
  if (!nav.seriesLoaded) return null;
  return (
    <div
      className={`chapter-end${raised ? ' chapter-end--raised' : ''}`}
      role="region"
      aria-label="Fim do capítulo"
      data-testid="chapter-end"
    >
      {nav.next ? (
        <Link className="btn btn--primary" to={nav.next.to} data-testid="next-chapter">
          Próximo capítulo ›
        </Link>
      ) : (
        <p className="chapter-end__text" data-testid="series-finished">
          Você chegou ao último capítulo.
        </p>
      )}
      {nav.previous && (
        <Link className="btn" to={nav.previous.to} data-testid="previous-chapter">
          ‹ Capítulo anterior
        </Link>
      )}
    </div>
  );
}
