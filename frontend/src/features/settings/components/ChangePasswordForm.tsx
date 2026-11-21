import { useChangePassword } from '../hooks/useChangePassword';

export function ChangePasswordForm() {
  const form = useChangePassword();
  return (
    <form className="settings__form" onSubmit={form.submit} noValidate data-testid="password-form">
      <label className="field">
        <span className="field__label">Senha atual</span>
        <input
          className="input"
          type="password"
          autoComplete="current-password"
          data-testid="password-current"
          value={form.current}
          onChange={(event) => form.setCurrent(event.target.value)}
        />
      </label>
      <label className="field">
        <span className="field__label">Nova senha</span>
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          data-testid="password-new"
          value={form.next}
          onChange={(event) => form.setNext(event.target.value)}
        />
      </label>
      <label className="field">
        <span className="field__label">Confirmar nova senha</span>
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          data-testid="password-confirm"
          value={form.confirm}
          onChange={(event) => form.setConfirm(event.target.value)}
        />
      </label>
      {form.feedback && (
        <p
          className={`alert alert--${form.feedback.kind}`}
          role={form.feedback.kind === 'error' ? 'alert' : 'status'}
          data-testid="password-feedback"
        >
          {form.feedback.text}
          {form.waiting ? ` (${form.remaining} s)` : ''}
        </p>
      )}
      <button
        type="submit"
        className="btn btn--primary"
        data-testid="password-submit"
        disabled={form.submitting || form.waiting}
      >
        {form.submitting ? 'Salvando…' : 'Alterar senha'}
      </button>
    </form>
  );
}
