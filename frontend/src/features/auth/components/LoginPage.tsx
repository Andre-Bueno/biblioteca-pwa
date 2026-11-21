import { Navigate, useLocation } from 'react-router-dom';
import { useSession } from '../../../shared/session';
import { safeRedirect } from '../hooks/safeRedirect';
import { useLoginForm } from '../hooks/useLoginForm';
import '../../../shared/ui';
import '../auth.css';

export function LoginPage() {
  const { status } = useSession();
  const location = useLocation();
  const form = useLoginForm();

  if (status === 'authenticated') {
    const from = (location.state as { from?: unknown } | null)?.from;
    return <Navigate to={safeRedirect(from)} replace />;
  }

  return (
    <main className="login" data-testid="login-page">
      <form className="login__card" onSubmit={form.submit} noValidate>
        <h1 className="login__title">Biblioteca</h1>
        <p className="muted">Entre para continuar lendo.</p>

        <label className="field">
          <span className="field__label">Usuário</span>
          <input
            className="input"
            name="username"
            data-testid="login-username"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={form.username}
            onChange={(event) => form.setUsername(event.target.value)}
          />
        </label>

        <label className="field">
          <span className="field__label">Senha</span>
          <input
            className="input"
            name="password"
            type="password"
            data-testid="login-password"
            autoComplete="current-password"
            value={form.password}
            onChange={(event) => form.setPassword(event.target.value)}
          />
        </label>

        {form.message && (
          <p className="alert alert--error" role="alert" data-testid="login-error">
            {form.message}
          </p>
        )}

        <button
          type="submit"
          className="btn btn--primary login__submit"
          data-testid="login-submit"
          disabled={!form.canSubmit}
        >
          {form.submitting ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </main>
  );
}
