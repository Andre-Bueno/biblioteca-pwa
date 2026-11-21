import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../../src/app/routes';
import { PreferencesProvider } from '../../src/shared/preferences';
import { SessionProvider } from '../../src/shared/session';
import { ThemeProvider } from '../../src/shared/theme';

/** The real provider stack and routes on a memory router (API mocked by tests/helpers/fake-api). */
export function renderApp(route = '/') {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[route]}>
        <SessionProvider>
          <PreferencesProvider>
            <AppRoutes />
          </PreferencesProvider>
        </SessionProvider>
      </MemoryRouter>
    </ThemeProvider>,
  );
}
