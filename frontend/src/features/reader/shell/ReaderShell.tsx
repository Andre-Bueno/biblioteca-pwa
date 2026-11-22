import type { ReadingDirection } from '../../../shared/preferences';
import type { SaveStatus } from '../../../shared/progress';
import type { ReaderNav } from '../../../shared/series';
import type { ReaderSource } from '../sources';
import { ReaderBars, type ZoomControl } from './ReaderBars';
import { ReaderEnd } from './ReaderEnd';
import { READER_TEXT } from './readerText';
import { SettingsDrawer, type TextSettings } from './SettingsDrawer';
import { TocDrawer } from './TocDrawer';
import type { Step } from './types';
import type { ReaderChrome, UnitSlider } from './useReaderChrome';
import './shell.css';

export interface ReaderShellProps {
  title: string;
  source: ReaderSource;
  nav: ReaderNav;
  /** The unit being read (0-based). */
  unit: number;
  /** Whole-item percent, 0 to 100. */
  percent: number;
  /** The reader reached the end of the unit: offer what comes next. */
  atEnd: boolean;
  mode: ReadingDirection;
  saveStatus: SaveStatus;
  chrome: ReaderChrome;
  slider: UnitSlider;
  onStep: (direction: Step) => void;
  onGoTo: (unit: number, anchor?: string | null) => void;
  onModeChange: (mode: ReadingDirection) => void;
  zoom: ZoomControl | null;
  text: TextSettings | null;
}

/**
 * The reader chrome that does not depend on the format: bars, position hint, save warning, end of
 * unit and the panels. What shows is driven by the {@link ReaderSource} (unit count, index,
 * capabilities); the reader renders the content itself and puts this next to it.
 */
export function ReaderShell({
  title,
  source,
  nav,
  unit,
  percent,
  atEnd,
  mode,
  saveStatus,
  chrome,
  slider,
  onStep,
  onGoTo,
  onModeChange,
  zoom,
  text,
}: ReaderShellProps) {
  const { capabilities } = source;
  const labels = READER_TEXT[source.kind];
  return (
    <>
      {saveStatus === 'error' && (
        <p className="reader-toast" role="status" data-testid="save-warning">
          Não foi possível salvar o progresso. Tentando novamente…
        </p>
      )}
      {!chrome.visible && (
        <button
          type="button"
          className="btn reader-reveal"
          aria-label="Mostrar controles"
          data-testid="show-controls"
          onClick={chrome.toggle}
        >
          ☰
        </button>
      )}
      {!chrome.visible && (
        <div
          className="reader-pill"
          {...(labels.announcePill
            ? { 'aria-live': 'polite' as const, 'aria-atomic': true }
            : { 'aria-hidden': true })}
          data-testid={labels.testIds.pill}
        >
          {labels.pill(unit, source.unitCount, percent)}
        </div>
      )}
      {atEnd && (
        <ReaderEnd source={source} nav={nav} unit={unit} raised={chrome.visible} onStep={onStep} />
      )}
      {chrome.visible && (
        <ReaderBars
          title={title}
          source={source}
          nav={nav}
          unit={unit}
          percent={percent}
          mode={mode}
          chrome={chrome}
          slider={slider}
          onStep={onStep}
          zoom={capabilities.zoomToggle ? zoom : null}
        />
      )}
      {chrome.panel === 'toc' && (
        <TocDrawer source={source} unit={unit} onGoTo={onGoTo} onClose={chrome.closePanel} />
      )}
      {chrome.panel === 'settings' && (
        <SettingsDrawer
          mode={mode}
          onModeChange={onModeChange}
          text={capabilities.textSettings ? text : null}
          prefsWarning={chrome.prefsWarning}
          onClose={chrome.closePanel}
        />
      )}
    </>
  );
}
