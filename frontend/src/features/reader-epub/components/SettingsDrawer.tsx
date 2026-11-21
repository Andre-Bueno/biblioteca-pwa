import { BOOK_FONT_MAX, BOOK_FONT_MIN, type BookTheme } from '../../../shared/preferences';
import { SegmentedControl, type SegmentedOption } from '../../../shared/ui';
import type { EpubReaderState } from '../hooks/useEpubReader';
import { Drawer } from './Drawer';

const THEME_OPTIONS: SegmentedOption<BookTheme>[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'light', label: 'Claro' },
  { value: 'dark', label: 'Escuro' },
  { value: 'sepia', label: 'Sépia' },
];

/** Reading settings: font size and book theme (saved in the user's preferences). */
export function SettingsDrawer({ reader }: { reader: EpubReaderState }) {
  return (
    <Drawer title="Ajustes de leitura" testId="reading-settings" onClose={reader.closePanel}>
      <div className="epub-setting">
        <span className="epub-setting__label" id="font-size-label">
          Tamanho do texto
        </span>
        <div className="epub-stepper" role="group" aria-labelledby="font-size-label">
          <button
            type="button"
            className="btn"
            aria-label="Diminuir o texto"
            disabled={reader.fontScale <= BOOK_FONT_MIN}
            data-testid="font-smaller"
            onClick={() => reader.setFontScale(-1)}
          >
            A-
          </button>
          <output className="epub-stepper__value" data-testid="font-value" aria-live="polite">
            {reader.fontScale}%
          </output>
          <button
            type="button"
            className="btn"
            aria-label="Aumentar o texto"
            disabled={reader.fontScale >= BOOK_FONT_MAX}
            data-testid="font-larger"
            onClick={() => reader.setFontScale(1)}
          >
            A+
          </button>
        </div>
      </div>
      <div className="epub-setting">
        <span className="epub-setting__label">Tema do livro</span>
        <SegmentedControl
          label="Tema do livro"
          options={THEME_OPTIONS}
          value={reader.theme}
          onChange={reader.setBookTheme}
          testId="book-theme"
        />
      </div>
      {(reader.prefsSaveFailed || reader.prefsLoadFailed) && (
        <p className="epub-drawer__empty" role="status" data-testid="prefs-warning">
          {reader.prefsLoadFailed
            ? 'Não foi possível carregar seus ajustes. As mudanças serão salvas quando a conexão voltar.'
            : 'Não foi possível salvar os ajustes agora. Eles continuam valendo nesta leitura.'}
        </p>
      )}
    </Drawer>
  );
}
