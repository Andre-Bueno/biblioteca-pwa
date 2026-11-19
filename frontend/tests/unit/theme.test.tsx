import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../../src/shared/theme';
import { ThemeToggle } from '../../src/shared/ui';

function mockMatchMedia(dark: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: dark,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
}

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
}

describe('theme', () => {
  beforeEach(() => {
    delete document.documentElement.dataset.theme;
  });

  it('follows the system preference by default', () => {
    mockMatchMedia(true);
    renderToggle();
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByRole('button', { name: 'Sistema' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('switches explicitly and does not touch localStorage', async () => {
    mockMatchMedia(false);
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    renderToggle();
    expect(document.documentElement.dataset.theme).toBe('light');
    await userEvent.click(screen.getByRole('button', { name: 'Escuro' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(setItem).not.toHaveBeenCalled();
  });
});
