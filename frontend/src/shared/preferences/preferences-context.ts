import { createContext } from 'react';
import type { Preferences } from './types';

export interface PreferencesContextValue {
  preferences: Preferences;
  /** False until the server answered (or failed): readers wait for it to pick the default mode. */
  loaded: boolean;
  /** True when the GET failed: edits are queued and saved after a successful reload. */
  loadFailed: boolean;
  /** True when the last save failed (the local value stays applied). */
  saveFailed: boolean;
  update: (patch: Partial<Preferences>) => Promise<void>;
  /** Tries to load the preferences again (after loadFailed). */
  reload: () => void;
}

export const PreferencesContext = createContext<PreferencesContextValue | null>(null);
