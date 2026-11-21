import { useState, type FormEvent } from 'react';
import { ApiError, NetworkError, RateLimitError } from '../../../shared/api-client';
import { useCountdown } from '../../../shared/hooks';
import { useSession } from '../../../shared/session';

type FailureKind = 'invalid' | 'rate' | 'busy' | 'network' | 'unknown';

// Used when the server omits Retry-After.
const FALLBACK_WAIT = { rate: 30, busy: 3 } as const;

function classify(error: unknown): { kind: FailureKind; wait: number | null } {
  if (error instanceof RateLimitError) return { kind: 'rate', wait: error.retryAfterSeconds };
  if (error instanceof ApiError) {
    if (error.status === 503) return { kind: 'busy', wait: error.retryAfterSeconds };
    // 401 and 422 get the same generic text: never say whether the user exists.
    if (error.status === 401 || error.status === 422) return { kind: 'invalid', wait: null };
    return { kind: 'unknown', wait: null };
  }
  if (error instanceof NetworkError) return { kind: 'network', wait: null };
  return { kind: 'unknown', wait: null };
}

export function useLoginForm() {
  const { login } = useSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<FailureKind | null>(null);
  const countdown = useCountdown();

  const waiting = countdown.remaining > 0;
  let message: string | null = null;
  if (failure === 'invalid') message = 'Usuário ou senha inválidos.';
  else if (failure === 'network') message = 'Não foi possível conectar ao servidor.';
  else if (failure === 'unknown') message = 'Não foi possível entrar. Tente novamente.';
  else if (failure === 'rate' && waiting)
    message = `Muitas tentativas. Tente novamente em ${countdown.remaining} s.`;
  else if (failure === 'busy' && waiting)
    message = `Servidor ocupado. Tente novamente em ${countdown.remaining} s.`;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting || waiting || !username || !password) return;
    setSubmitting(true);
    setFailure(null);
    try {
      await login(username, password);
      // The session context flips to authenticated; the page redirects on its own.
    } catch (error) {
      const { kind, wait } = classify(error);
      setFailure(kind);
      if (kind === 'rate') countdown.start(wait ?? FALLBACK_WAIT.rate);
      else if (kind === 'busy') countdown.start(wait ?? FALLBACK_WAIT.busy);
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  }

  return {
    username,
    password,
    setUsername,
    setPassword,
    submitting,
    waiting,
    message,
    canSubmit: !submitting && !waiting && username !== '' && password !== '',
    submit,
  };
}
