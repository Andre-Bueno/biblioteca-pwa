import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError, apiClient } from '../api-client';
import { fetchMe, postChangePassword, postLogin, postLogout } from './api';
import { SessionContext } from './session-context';
import type { SessionStatus, SessionUser } from './types';
import { useSessionKeepAlive } from './useSessionKeepAlive';

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [user, setUser] = useState<SessionUser | null>(null);
  const [checkToken, setCheckToken] = useState(0);

  // Initial load: /auth/me (the api-client refreshes once if the access cookie has expired).
  // ONLY a 401 means "signed out"; 429/503/offline are recoverable and keep the user's state.
  useEffect(() => {
    const controller = new AbortController();
    fetchMe(controller.signal)
      .then((me) => {
        setUser(me);
        setStatus('authenticated');
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          setStatus('anonymous');
        } else {
          setStatus('error');
        }
      });
    return () => controller.abort();
  }, [checkToken]);

  const retry = useCallback(() => {
    setStatus('loading');
    setCheckToken((value) => value + 1);
  }, []);

  // A refresh that is rejected anywhere in the app ends the session and sends us to the login.
  useEffect(
    () =>
      apiClient.onSessionExpired(() => {
        setUser(null);
        setStatus('anonymous');
      }),
    [],
  );

  useSessionKeepAlive(status === 'authenticated');

  const login = useCallback(async (username: string, password: string) => {
    const me = await postLogin(username, password);
    setUser(me);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(async () => {
    try {
      await postLogout();
    } catch {
      // Ignored on purpose: the local session is dropped below either way.
    } finally {
      setUser(null);
      setStatus('anonymous');
    }
  }, []);

  const value = useMemo(
    () => ({ status, user, login, logout, changePassword: postChangePassword, retry }),
    [status, user, login, logout, retry],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
