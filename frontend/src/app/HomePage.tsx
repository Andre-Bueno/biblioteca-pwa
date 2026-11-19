import { ThemeToggle } from '../shared/ui';
import { useHealth } from './useHealth';

const LABELS = { loading: 'Verificando…', ok: 'Servidor online', error: 'Servidor indisponível' };

export function HomePage() {
  const health = useHealth();
  return (
    <main className="page">
      <h1>Biblioteca</h1>
      <p className={`status status--${health.status}`} role="status">
        {LABELS[health.status]}
      </p>
      {health.status === 'error' && <p className="muted">{health.message}</p>}
      <ThemeToggle />
    </main>
  );
}
