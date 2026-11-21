import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useSession } from '../../../shared/session';
import '../../../shared/ui';

/** Route guard: waits for /auth/me, sends anonymous users to /login and remembers where to return. */
export function RequireAuth() {
  const { status, retry } = useSession();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div className="splash" role="status" aria-label="Carregando" data-testid="session-loading">
        <div className="spinner" />
      </div>
    );
  }
  if (status === 'error') {
    // Could not verify the session (offline, rate limited, server busy): not a sign-out.
    return (
      <div className="splash" data-testid="session-error">
        <div role="alert" className="splash__box">
          <p>Não foi possível verificar a sessão.</p>
          <button type="button" className="btn" onClick={retry} data-testid="session-retry">
            Tentar de novo
          </button>
        </div>
      </div>
    );
  }
  if (status === 'anonymous') {
    return (
      <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
    );
  }
  return <Outlet />;
}
