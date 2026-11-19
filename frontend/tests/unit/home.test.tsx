import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HomePage } from '../../src/app/HomePage';
import { ThemeProvider } from '../../src/shared/theme';

vi.mock('../../src/shared/api-client', () => ({
  apiClient: { get: vi.fn().mockResolvedValue({ status: 'ok' }) },
}));

describe('HomePage', () => {
  it('shows the health status from the API', async () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(
      <ThemeProvider>
        <HomePage />
      </ThemeProvider>,
    );
    expect(await screen.findByText('Servidor online')).toBeInTheDocument();
  });
});
