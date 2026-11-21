import { Link } from 'react-router-dom';
import type { EpubReaderState } from '../hooks/useEpubReader';

/** Top bar (back, title, TOC, settings) and bottom bar (chapter navigation, slider). */
export function EpubControls({ reader }: { reader: EpubReaderState }) {
  const { nav, count, chapter } = reader;
  const title = reader.book.title || reader.item.title;
  return (
    // Any touch, key or focus inside the bars restarts the auto-hide wait.
    <div
      data-testid="reader-controls"
      onPointerDownCapture={reader.keepControlsAlive}
      onFocusCapture={reader.keepControlsAlive}
      onKeyDownCapture={reader.keepControlsAlive}
      onChangeCapture={reader.keepControlsAlive}
    >
      <header className="epub-bar epub-bar--top">
        <Link className="btn" to={nav.backTo} aria-label={nav.backLabel} data-testid="reader-back">
          ‹ Voltar
        </Link>
        <h1 className="epub-bar__title" data-testid="book-title">
          {title}
        </h1>
        <button
          type="button"
          className="btn"
          aria-haspopup="dialog"
          data-testid="open-toc"
          onClick={() => reader.openPanel('toc')}
        >
          Índice
        </button>
        <button
          type="button"
          className="btn"
          aria-haspopup="dialog"
          aria-label="Ajustes de leitura"
          data-testid="open-settings"
          onClick={() => reader.openPanel('settings')}
        >
          Aa
        </button>
      </header>
      <footer className="epub-bar epub-bar--bottom">
        <input
          className="epub-slider"
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          step={1}
          value={reader.sliderValue}
          aria-label="Ir para o capítulo"
          aria-valuetext={`Capítulo ${reader.sliderValue + 1} de ${count}`}
          disabled={count <= 1}
          data-testid="chapter-slider"
          onChange={(event) => reader.setSliderValue(Number(event.target.value))}
        />
        <div className="epub-bar__row">
          <button
            type="button"
            className="btn"
            aria-label="Capítulo anterior"
            disabled={chapter <= 0}
            data-testid="chapter-prev"
            onClick={() => reader.step('chapter-prev')}
          >
            ‹
          </button>
          <span
            className="epub-bar__status"
            aria-live="polite"
            aria-atomic="true"
            data-testid="chapter-indicator"
          >
            Capítulo {chapter + 1} de {count} · {reader.percent}%
          </span>
          <button
            type="button"
            className="btn"
            aria-label="Próximo capítulo"
            disabled={chapter >= count - 1}
            data-testid="chapter-next"
            onClick={() => reader.step('chapter-next')}
          >
            ›
          </button>
        </div>
      </footer>
    </div>
  );
}
