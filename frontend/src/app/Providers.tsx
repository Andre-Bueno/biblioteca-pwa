import type { ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { PreferencesProvider } from '../shared/preferences';
import { SessionProvider } from '../shared/session';
import { VersionProvider } from '../shared/system';
import { ThemeProvider } from '../shared/theme';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <SessionProvider>
          <PreferencesProvider>
            <VersionProvider>{children}</VersionProvider>
          </PreferencesProvider>
        </SessionProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
