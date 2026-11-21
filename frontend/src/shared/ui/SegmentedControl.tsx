import './ui.css';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  testId?: string;
}

export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  testId,
}: SegmentedControlProps<T>) {
  return (
    <div className="segmented" role="group" aria-label={label} data-testid={testId}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="segmented__button"
          aria-pressed={value === option.value}
          data-testid={testId ? `${testId}-${option.value}` : undefined}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
