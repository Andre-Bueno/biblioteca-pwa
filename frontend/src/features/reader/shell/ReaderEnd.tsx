import { Link } from 'react-router-dom';
import type { ReaderNav } from '../../../shared/series';
import type { ReaderSource } from '../sources';
import { READER_TEXT } from './readerText';
import type { Step } from './types';

interface ReaderEndProps {
  source: ReaderSource;
  nav: ReaderNav;
  unit: number;
  /** The bars are up: sit above them. */
  raised: boolean;
  onStep: (direction: Step) => void;
}

/**
 * Shown at the end of a unit: the next unit while there is one, and at the very end the neighbours
 * in the series (next / previous) with a short note.
 */
export function ReaderEnd({ source, nav, unit, raised, onStep }: ReaderEndProps) {
  const { end } = READER_TEXT[source.kind];
  const isLast = unit >= source.unitCount - 1;
  if (isLast && end.needsSeries && !nav.seriesLoaded) return null;

  return (
    <div
      className={`reader-end${raised ? ' reader-end--raised' : ''}`}
      role="region"
      aria-label={isLast ? end.lastRegion : 'Fim do capítulo'}
      data-testid="chapter-end"
    >
      {isLast ? (
        <>
          {nav.next && (
            <Link className="btn btn--primary" to={nav.next.to} data-testid={end.next.testId}>
              {end.next.label}
            </Link>
          )}
          {(end.finished.alwaysShown || !nav.next) && (
            <p className="reader-end__text" data-testid={end.finished.testId}>
              {end.finished.text}
            </p>
          )}
          {nav.previous && (
            <Link className="btn" to={nav.previous.to} data-testid={end.previous.testId}>
              {end.previous.label}
            </Link>
          )}
        </>
      ) : (
        <button
          type="button"
          className="btn btn--primary"
          data-testid="end-next-chapter"
          onClick={() => onStep('next')}
        >
          Próximo capítulo ›
        </button>
      )}
    </div>
  );
}
