export interface SessionUser {
  id: string;
  username: string;
  role: string;
  theme_pref?: string | null;
}

/**
 * `error`: the session could not be verified (offline, 429, 503...). It is NOT a sign-out: the
 * UI offers a retry instead of sending the user to the login.
 */
export type SessionStatus = 'loading' | 'authenticated' | 'anonymous' | 'error';
