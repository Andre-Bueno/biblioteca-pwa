import { Link } from 'react-router-dom';
import type { ReadingDirection } from '../../../shared/preferences';
import type { ReaderNav } from '../../../shared/series';
import type { ReaderSource } from '../sources';
import { READER_TEXT } from './readerText';
import type { Step } from './types';
import type { ReaderChrome, UnitSlider } from './useReaderChrome';

export interface ZoomControl {
  active: boolean;
  toggle: () => void;
}

interface ReaderBarsProps {
  title: string;
  source: ReaderSource;
  nav: ReaderNav;
  unit: number;
  percent: number;
  mode: ReadingDirection;
  chrome: ReaderChrome;
  slider: UnitSlider;
  onStep: (direction: Step) => void;
  /** Present only when the zoom toggle applies to what is on screen. */
  zoom: ZoomControl | null;
}

/** Top bar (back, title, index, settings) and bottom bar (slider, previous/next, status, zoom). */
export function ReaderBars({
  title,
  source,
  nav,
  unit,
  percent,
  mode,
  chrome,
  slider,
  onStep,
  zoom,
}: ReaderBarsProps) {
  const { unitCount } = source;
  const text = READER_TEXT[source.kind];
  return (
    // Any touch, key or focus inside the bars restarts the auto-hide wait.
    <div
      data-testid="reader-controls"
      onPointerDownCapture={chrome.keepAlive}
      onFocusCapture={chrome.keepAlive}
      onKeyDownCapture={chrome.keepAlive}
      onChangeCapture={chrome.keepAlive}
    >
      <header className="reader-bar reader-bar--top">
        <Link className="btn" to={nav.backTo} aria-label={nav.backLabel} data-testid="reader-back">
          ‹ Voltar
        </Link>
        <h1 className="reader-bar__title" data-testid={text.testIds.title}>
          {title}
        </h1>
        {source.toc && (
          <button
            type="button"
            className="btn"
            aria-haspopup="dialog"
            data-testid="open-toc"
            onClick={() => chrome.openPanel('toc')}
          >
            Índice
          </button>
        )}
        <button
          type="button"
          className="btn"
          aria-haspopup="dialog"
          aria-label="Ajustes de leitura"
          data-testid="open-settings"
          onClick={() => chrome.openPanel('settings')}
        >
          Aa
        </button>
      </header>
      <footer className="reader-bar reader-bar--bottom">
        <input
          className="reader-slider"
          type="range"
          min={0}
          max={Math.max(0, unitCount - 1)}
          step={1}
          value={slider.value}
          // In right-to-left mode the thumb moves from right to left, like the pages.
          dir={source.capabilities.honorsDirection && mode === 'rtl' ? 'rtl' : 'ltr'}
          aria-label={text.sliderLabel}
          aria-valuetext={`${text.unitName} ${slider.value + 1} de ${unitCount}`}
          disabled={unitCount <= 1}
          data-testid={text.testIds.slider}
          {...chrome.dragHandlers}
          onChange={(event) => slider.onChange(Number(event.target.value))}
        />
        <div className="reader-bar__row">
          <button
            type="button"
            className="btn"
            aria-label={text.prevLabel}
            disabled={unit <= 0}
            data-testid={text.testIds.prev}
            onClick={() => onStep('prev')}
          >
            ‹
          </button>
          <span
            className="reader-bar__status"
            aria-live="polite"
            aria-atomic="true"
            data-testid={text.testIds.status}
          >
            {text.status(unit, unitCount, percent)}
          </span>
          <button
            type="button"
            className="btn"
            aria-label={text.nextLabel}
            disabled={unit >= unitCount - 1}
            data-testid={text.testIds.next}
            onClick={() => onStep('next')}
          >
            ›
          </button>
          {zoom && (
            <button
              type="button"
              className="btn"
              aria-pressed={zoom.active}
              data-testid="zoom-toggle"
              onClick={zoom.toggle}
            >
              {zoom.active ? 'Reduzir' : 'Ampliar'}
            </button>
          )}
        </div>
      </footer>
    </div>
  );
}
