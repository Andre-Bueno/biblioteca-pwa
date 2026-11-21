import { useTheme, type ThemePreference } from '../theme';
import { SegmentedControl, type SegmentedOption } from './SegmentedControl';

const OPTIONS: SegmentedOption<ThemePreference>[] = [
  { value: 'system', label: 'Sistema' },
  { value: 'light', label: 'Claro' },
  { value: 'dark', label: 'Escuro' },
];

interface ThemeToggleProps {
  /** Extra hook for callers that persist the choice (e.g. on the server). */
  onSelect?: (preference: ThemePreference) => void;
}

export function ThemeToggle({ onSelect }: ThemeToggleProps) {
  const { preference, setPreference } = useTheme();
  return (
    <SegmentedControl
      label="Tema"
      options={OPTIONS}
      value={preference}
      testId="theme-toggle"
      onChange={(next) => {
        setPreference(next);
        onSelect?.(next);
      }}
    />
  );
}
