export type ReadingDirection = 'rtl' | 'ltr' | 'vertical';
export type ThemeChoice = 'system' | 'light' | 'dark';

export interface Preferences {
  theme: ThemeChoice;
  reading_direction: ReadingDirection;
}

export const DEFAULT_PREFERENCES: Preferences = { theme: 'system', reading_direction: 'rtl' };

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === 'system' || value === 'light' || value === 'dark';
}

export function isReadingDirection(value: unknown): value is ReadingDirection {
  return value === 'rtl' || value === 'ltr' || value === 'vertical';
}

/** Server data is not trusted to be well-formed: keep valid fields, default the rest. */
export function normalizePreferences(raw: unknown): Preferences {
  const data = (raw ?? {}) as Partial<Record<keyof Preferences, unknown>>;
  return {
    theme: isThemeChoice(data.theme) ? data.theme : DEFAULT_PREFERENCES.theme,
    reading_direction: isReadingDirection(data.reading_direction)
      ? data.reading_direction
      : DEFAULT_PREFERENCES.reading_direction,
  };
}
