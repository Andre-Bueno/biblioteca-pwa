import {
  BOOK_FONT_MAX,
  BOOK_FONT_MIN,
  type BookTheme,
  type ReadingDirection,
} from '../../../shared/preferences';
import { SegmentedControl, type SegmentedOption } from '../../../shared/ui';
import { Drawer } from './Drawer';
import type { PrefsWarning } from './useReaderChrome';

const THEME_OPTIONS: SegmentedOption<BookTheme>[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'light', label: 'Claro' },
  { value: 'dark', label: 'Escuro' },
  { value: 'sepia', label: 'Sépia' },
];

const MODE_OPTIONS: SegmentedOption<ReadingDirection>[] = [
  { value: 'rtl', label: 'D→E' },
  { value: 'ltr', label: 'E→D' },
  { value: 'vertical', label: 'Vertical' },
];

/** Font size and theme of a text source. */
export interface TextSettings {
  fontScale: number;
  theme: BookTheme;
  setFontScale: (direction: 1 | -1) => void;
  setTheme: (theme: BookTheme) => void;
}

interface SettingsDrawerProps {
  mode: ReadingDirection;
  onModeChange: (mode: ReadingDirection) => void;
  /** Only for sources whose text can be resized and themed. */
  text: TextSettings | null;
  prefsWarning: PrefsWarning;
  onClose: () => void;
}

/** Reading settings: reading mode for every format; font and theme only for text. */
export function SettingsDrawer({
  mode,
  onModeChange,
  text,
  prefsWarning,
  onClose,
}: SettingsDrawerProps) {
  return (
    <Drawer title="Ajustes de leitura" testId="reading-settings" onClose={onClose}>
      <div className="reader-setting">
        <span className="reader-setting__label">Modo de leitura</span>
        <SegmentedControl
          label="Modo de leitura"
          options={MODE_OPTIONS}
          value={mode}
          onChange={onModeChange}
          testId="reader-mode"
        />
      </div>
      {text && (
        <>
          <div className="reader-setting">
            <span className="reader-setting__label" id="font-size-label">
              Tamanho do texto
            </span>
            <div className="reader-stepper" role="group" aria-labelledby="font-size-label">
              <button
                type="button"
                className="btn"
                aria-label="Diminuir o texto"
                disabled={text.fontScale <= BOOK_FONT_MIN}
                data-testid="font-smaller"
                onClick={() => text.setFontScale(-1)}
              >
                A-
              </button>
              <output className="reader-stepper__value" data-testid="font-value" aria-live="polite">
                {text.fontScale}%
              </output>
              <button
                type="button"
                className="btn"
                aria-label="Aumentar o texto"
                disabled={text.fontScale >= BOOK_FONT_MAX}
                data-testid="font-larger"
                onClick={() => text.setFontScale(1)}
              >
                A+
              </button>
            </div>
          </div>
          <div className="reader-setting">
            <span className="reader-setting__label">Tema do livro</span>
            <SegmentedControl
              label="Tema do livro"
              options={THEME_OPTIONS}
              value={text.theme}
              onChange={text.setTheme}
              testId="book-theme"
            />
          </div>
        </>
      )}
      {prefsWarning && (
        <p className="reader-drawer__empty" role="status" data-testid="prefs-warning">
          {prefsWarning === 'load'
            ? 'Não foi possível carregar seus ajustes. As mudanças serão salvas quando a conexão voltar.'
            : 'Não foi possível salvar os ajustes agora. Eles continuam valendo nesta leitura.'}
        </p>
      )}
    </Drawer>
  );
}
