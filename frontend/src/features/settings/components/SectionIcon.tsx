export type SectionIconName = 'appearance' | 'reading' | 'about' | 'account';

const PATHS = {
  appearance: 'M12 3a9 9 0 1 0 9 9c0-.5-.4-.9-.9-.8A5.5 5.5 0 0 1 12.8 3.9c.1-.5-.3-.9-.8-.9z',
  reading:
    'M4 5.5C6.5 4.5 9.5 4.5 12 6c2.5-1.5 5.5-1.5 8-.5V19c-2.5-1-5.5-1-8 .5-2.5-1.5-5.5-1.5-8-.5z M12 6v13.5',
  about: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 11v5.5 M12 7.6v.1',
  account: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 20c.8-3.6 3.7-5.5 7.5-5.5s6.7 1.9 7.5 5.5',
} as const satisfies Record<SectionIconName, string>;

function pathFor(name: SectionIconName): string {
  return (
    new Map<SectionIconName, string>(Object.entries(PATHS) as [SectionIconName, string][]).get(
      name,
    ) ?? ''
  );
}

/** Decorative line icon (the section title already carries the meaning). */
export function SectionIcon({ name }: { name: SectionIconName }) {
  return (
    <svg
      className="settings__icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={pathFor(name)} />
    </svg>
  );
}
