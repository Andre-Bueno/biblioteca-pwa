import { createContext } from 'react';
import type { SessionStatus, SessionUser } from './types';

export interface SessionContextValue {
  status: SessionStatus;
  user: SessionUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  /** Checks the session again after status === 'error'. */
  retry: () => void;
}

export const SessionContext = createContext<SessionContextValue | null>(null);
