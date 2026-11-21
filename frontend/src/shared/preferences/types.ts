export type ReadingDirection = 'rtl' | 'ltr' | 'vertical';
export type ThemeChoice = 'system' | 'light' | 'dark';
/** Theme of the book text (applied by the server to the chapter document). */
export type BookTheme = 'auto' | 'light' | 'dark' | 'sepia';

export const BOOK_FONT_MIN = 80;
export const BOOK_FONT_MAX = 200;

export interface Preferences {
  theme: ThemeChoice;
  reading_direction: ReadingDirection;
  /** Percent, 80 to 200. */
  book_font_scale: number;
  book_theme: BookTheme;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: 'system',
  reading_direction: 'rtl',
  book_font_scale: 100,
  book_theme: 'auto',
};

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === 'system' || value === 'light' || value === 'dark';
}

export function isReadingDirection(value: unknown): value is ReadingDirection {
  return value === 'rtl' || value === 'ltr' || value === 'vertical';
}

export function isBookTheme(value: unknown): value is BookTheme {
  return value === 'auto' || value === 'light' || value === 'dark' || value === 'sepia';
}

export function isBookFontScale(value: unknown): value is number {
  return (
    typeof value === 'number' &&
    Number.isInteger(value) &&
    value >= BOOK_FONT_MIN &&
    value <= BOOK_FONT_MAX
  );
}

/** Server data is not trusted to be well-formed: keep valid fields, default the rest. */
export function normalizePreferences(raw: unknown): Preferences {
  const data = (raw ?? {}) as Partial<Record<keyof Preferences, unknown>>;
  return {
    theme: isThemeChoice(data.theme) ? data.theme : DEFAULT_PREFERENCES.theme,
    reading_direction: isReadingDirection(data.reading_direction)
      ? data.reading_direction
      : DEFAULT_PREFERENCES.reading_direction,
    book_font_scale: isBookFontScale(data.book_font_scale)
      ? data.book_font_scale
      : DEFAULT_PREFERENCES.book_font_scale,
    book_theme: isBookTheme(data.book_theme) ? data.book_theme : DEFAULT_PREFERENCES.book_theme,
  };
}
