import type { ReaderSource, TocItem } from '../sources';
import { Drawer } from './Drawer';

interface TocDrawerProps {
  source: ReaderSource;
  /** The unit being read, to mark its entry. */
  unit: number;
  onGoTo: (unit: number, anchor: string | null) => void;
  onClose: () => void;
}

/** Table of contents; falls back to the list of units when the source has no entries. */
export function TocDrawer({ source, unit, onGoTo, onClose }: TocDrawerProps) {
  const entries: TocItem[] =
    source.toc && source.toc.length > 0
      ? [...source.toc]
      : Array.from({ length: source.unitCount }, (_, index) => ({
          title: source.unitTitle(index),
          unit: index,
          anchor: null,
        }));
  const currentPosition = entries.findIndex((entry) => entry.unit === unit);

  return (
    <Drawer title="Índice" testId="toc" onClose={onClose}>
      {/* The gate never mounts a reader without units, so there is always something to list. */}
      <ul className="reader-toc" data-testid="toc-list">
        {entries.map((entry, position) => (
          <li key={position}>
            <button
              type="button"
              className="reader-toc__item"
              aria-current={position === currentPosition ? 'true' : undefined}
              data-testid="toc-item"
              onClick={() => onGoTo(entry.unit, entry.anchor)}
            >
              {entry.title || source.unitTitle(entry.unit)}
            </button>
          </li>
        ))}
      </ul>
    </Drawer>
  );
}
