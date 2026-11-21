import { useState, type FormEvent } from 'react';
import { ApiError, NetworkError, RateLimitError } from '../../../shared/api-client';
import { useCountdown } from '../../../shared/hooks';
import { useSession } from '../../../shared/session';

export type PasswordFeedback = { kind: 'success' | 'error'; text: string } | null;

export function useChangePassword() {
  const { changePassword } = useSession();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<PasswordFeedback>(null);
  const [blocked, setBlocked] = useState(false);
  const countdown = useCountdown();

  const waiting = blocked && countdown.remaining > 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting || waiting) return;
    if (!current || !next) {
      setFeedback({ kind: 'error', text: 'Preencha a senha atual e a nova senha.' });
      return;
    }
    if (next !== confirm) {
      setFeedback({ kind: 'error', text: 'A confirmação não é igual à nova senha.' });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      await changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      setFeedback({ kind: 'success', text: 'Senha alterada com sucesso.' });
    } catch (error) {
      setFeedback({ kind: 'error', text: describe(error) });
      if (error instanceof RateLimitError || (error instanceof ApiError && error.status === 503)) {
        setBlocked(true);
        countdown.start(error.retryAfterSeconds ?? 10);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return {
    current,
    next,
    confirm,
    setCurrent,
    setNext,
    setConfirm,
    submitting,
    waiting,
    remaining: countdown.remaining,
    feedback,
    submit,
  };
}

function describe(error: unknown): string {
  if (error instanceof RateLimitError) return 'Muitas tentativas. Aguarde e tente novamente.';
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) return 'A senha atual está incorreta.';
    if (error.status === 422) {
      return 'A nova senha não atende aos requisitos ou é igual à senha atual.';
    }
    if (error.status === 503) return 'Servidor ocupado. Tente novamente em instantes.';
  }
  if (error instanceof NetworkError) return 'Não foi possível conectar ao servidor.';
  return 'Não foi possível alterar a senha. Tente novamente.';
}
