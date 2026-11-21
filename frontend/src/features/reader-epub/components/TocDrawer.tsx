import type { EpubReaderState } from '../hooks/useEpubReader';
import { Drawer } from './Drawer';

interface Entry {
  key: string;
  title: string;
  index: number;
  anchor: string | null;
}

/** Table of contents; falls back to the chapter list when the book has no TOC. */
export function TocDrawer({ reader }: { reader: EpubReaderState }) {
  const { book } = reader;
  const source: Entry[] =
    book.toc.length > 0
      ? book.toc.map((entry, position) => ({ ...entry, key: `toc-${position}` }))
      : book.chapters.map((entry) => ({ ...entry, anchor: null, key: `ch-${entry.index}` }));
  const currentPosition = source.findIndex((entry) => entry.index === reader.chapter);

  return (
    <Drawer title="Índice" testId="toc" onClose={reader.closePanel}>
      {source.length === 0 ? (
        <p className="epub-drawer__empty" data-testid="toc-empty">
          Este livro não tem índice.
        </p>
      ) : (
        <ul className="epub-toc" data-testid="toc-list">
          {source.map((entry, position) => (
            <li key={entry.key}>
              <button
                type="button"
                className="epub-toc__item"
                aria-current={position === currentPosition ? 'true' : undefined}
                data-testid="toc-item"
                onClick={() => reader.goToChapter(entry.index, entry.anchor)}
              >
                {entry.title || `Capítulo ${entry.index + 1}`}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Drawer>
  );
}
