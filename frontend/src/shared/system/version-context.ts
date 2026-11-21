import { createContext } from 'react';
import type { VersionInfo } from './types';

export interface VersionContextValue {
  /** Null until the first answer (or when it failed: failures are silent). */
  info: VersionInfo | null;
  /** Tag of the release the admin chose "Agora não" for (until the page is reloaded). */
  dismissedTag: string | null;
  dismiss: (tag: string) => void;
  /** Explicit admin check (POST). Rejects with the ApiError so the caller can explain. */
  check: () => Promise<VersionInfo>;
  /** Replaces the known info (e.g. after the update polling saw the new version). */
  applyInfo: (info: VersionInfo) => void;
}

export const VersionContext = createContext<VersionContextValue | null>(null);
