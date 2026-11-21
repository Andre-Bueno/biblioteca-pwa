import { Link } from 'react-router-dom';
import type { EpubReaderState } from '../hooks/useEpubReader';

/** Shown at the end of a chapter: next chapter, or the end of the book with a shortcut. */
export function EpubEnd({ reader }: { reader: EpubReaderState }) {
  const { nav } = reader;
  return (
    <div
      className={`epub-end${reader.controlsVisible ? ' epub-end--raised' : ''}`}
      role="region"
      aria-label={reader.isLastChapter ? 'Fim do livro' : 'Fim do capítulo'}
      data-testid="chapter-end"
    >
      {reader.isLastChapter ? (
        <>
          <p className="epub-end__text" data-testid="book-finished">
            Você chegou ao fim do livro.
          </p>
          {nav.next && (
            <Link className="btn btn--primary" to={nav.next.to} data-testid="next-book">
              Próximo livro ›
            </Link>
          )}
        </>
      ) : (
        <button
          type="button"
          className="btn btn--primary"
          data-testid="end-next-chapter"
          onClick={() => reader.step('chapter-next')}
        >
          Próximo capítulo ›
        </button>
      )}
    </div>
  );
}
