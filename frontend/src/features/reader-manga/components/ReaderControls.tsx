import { Link } from 'react-router-dom';
import { SegmentedControl, type SegmentedOption } from '../../../shared/ui';
import type { ReaderNav } from '../../../shared/series';
import type { ReaderState } from '../hooks/useReaderState';
import type { ReaderMode } from '../navigation';

const MODE_OPTIONS: SegmentedOption<ReaderMode>[] = [
  { value: 'rtl', label: 'D→E' },
  { value: 'ltr', label: 'E→D' },
  { value: 'vertical', label: 'Vertical' },
];

export function ReaderControls({ reader, nav }: { reader: ReaderState; nav: ReaderNav }) {
  return (
    <div data-testid="reader-controls">
      <header className="reader-bar reader-bar--top">
        <Link className="btn" to={nav.backTo} aria-label={nav.backLabel} data-testid="reader-back">
          ‹ Voltar
        </Link>
        <h1 className="reader-bar__title">{reader.item.title}</h1>
        <SegmentedControl
          label="Modo de leitura"
          options={MODE_OPTIONS}
          value={reader.mode}
          onChange={reader.changeMode}
          testId="reader-mode"
        />
      </header>
      <footer className="reader-bar reader-bar--bottom">
        <input
          className="reader-slider"
          type="range"
          min={1}
          max={reader.pageCount}
          step={1}
          value={reader.page + 1}
          // In right-to-left mode the thumb moves from right to left, like the pages.
          dir={reader.mode === 'rtl' ? 'rtl' : 'ltr'}
          aria-label="Ir para a página"
          data-testid="page-slider"
          onChange={(event) => reader.goTo(Number(event.target.value) - 1)}
        />
        {reader.mode !== 'vertical' && (
          <button
            type="button"
            className="btn"
            aria-pressed={reader.zoomed}
            data-testid="zoom-toggle"
            onClick={reader.toggleZoom}
          >
            {reader.zoomed ? 'Reduzir' : 'Ampliar'}
          </button>
        )}
      </footer>
    </div>
  );
}
