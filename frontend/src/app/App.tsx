import { AppUpdatePrompt } from './AppUpdatePrompt';
import { Providers } from './Providers';
import { AppRoutes } from './routes';

export function App() {
  return (
    <Providers>
      <AppUpdatePrompt />
      <AppRoutes />
    </Providers>
  );
}
