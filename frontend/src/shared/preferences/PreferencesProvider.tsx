import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useSession } from '../session';
import { useTheme } from '../theme';
import { fetchPreferences, savePreferences } from './api';
import { PreferencesContext } from './preferences-context';
import { DEFAULT_PREFERENCES, isThemeChoice, type Preferences } from './types';

interface Remote {
  userId: string;
  preferences: Preferences;
}

/**
 * Loads /me/preferences once signed in and applies the theme right away.
 *
 * The server is the source of truth, so a PUT is ALWAYS the complete object built on what the
 * server returned: until the GET succeeds, edits are only queued (and the theme applied
 * locally); they are merged into the server data and saved when the GET finally answers.
 * PUTs are serialized (one in flight; the latest value wins), so they reach the server in order.
 * Loaded data is stored with the user id it belongs to, so a sign-out/in as someone else can
 * never show the previous user's values.
 */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const { status, user } = useSession();
  const { setPreference } = useTheme();
  const [remote, setRemote] = useState<Remote | null>(null);
  const [queued, setQueued] = useState<{ userId: string; patch: Partial<Preferences> } | null>(
    null,
  );
  const [settledFor, setSettledFor] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [saveFailed, setSaveFailed] = useState(false);

  // Mutable save state (not rendered): see the class comment above.
  const desired = useRef<Preferences | null>(null); // full object the server should end up with
  const sent = useRef<string | null>(null); // JSON of the last object the server acknowledged
  const queuedPatch = useRef<Partial<Preferences>>({});
  const inflight = useRef(false);

  const userId = status === 'authenticated' && user ? user.id : null;
  const ready = userId !== null && remote?.userId === userId;
  const preferences = useMemo(() => {
    if (userId !== null && remote?.userId === userId) return remote.preferences;
    // Not loaded: defaults plus whatever the user already picked (queued, never saved from here).
    const patch = userId !== null && queued?.userId === userId ? queued.patch : {};
    return { ...DEFAULT_PREFERENCES, ...patch };
  }, [userId, remote, queued]);
  const loaded = userId !== null && settledFor === userId;
  const loadFailed = loaded && !ready;

  useEffect(() => {
    if (status === 'anonymous') setPreference('system');
  }, [status, setPreference]);

  const pump = useCallback(async () => {
    if (inflight.current) return; // the running loop will pick the newest value up
    inflight.current = true;
    try {
      while (desired.current !== null && JSON.stringify(desired.current) !== sent.current) {
        const snapshot = desired.current;
        try {
          await savePreferences(snapshot);
          sent.current = JSON.stringify(snapshot);
          setSaveFailed(false);
        } catch {
          setSaveFailed(true);
          return; // the next edit (or a reload) tries again
        }
      }
    } finally {
      inflight.current = false;
    }
  }, []);

  useEffect(() => {
    if (userId === null) return;
    // New load for this user: forget any save state of a previous one.
    desired.current = null;
    sent.current = null;
    // /auth/me already carries theme_pref: apply it before /me/preferences answers.
    if (isThemeChoice(user?.theme_pref)) setPreference(user.theme_pref);

    const controller = new AbortController();
    fetchPreferences(controller.signal)
      .then((data) => {
        // Edits made while the GET was pending/failing go on top of the SERVER data.
        const full = { ...data, ...queuedPatch.current };
        queuedPatch.current = {};
        desired.current = full;
        sent.current = JSON.stringify(data);
        setRemote({ userId, preferences: full });
        setQueued(null);
        setPreference(full.theme);
        void pump();
      })
      .catch(() => undefined) // stay on defaults; the settings screen offers a retry
      .finally(() => {
        if (!controller.signal.aborted) setSettledFor(userId);
      });
    return () => controller.abort();
  }, [userId, user?.theme_pref, setPreference, pump, retryToken]);

  const update = useCallback(
    async (patch: Partial<Preferences>) => {
      if (userId === null) return;
      if (patch.theme) setPreference(patch.theme); // immediate, before the network answers
      if (desired.current === null) {
        // Server data not known yet: never build a PUT from defaults.
        queuedPatch.current = { ...queuedPatch.current, ...patch };
        setQueued({ userId, patch: queuedPatch.current });
        return;
      }
      desired.current = { ...desired.current, ...patch };
      setRemote({ userId, preferences: desired.current });
      await pump();
    },
    [userId, setPreference, pump],
  );

  const reload = useCallback(() => setRetryToken((value) => value + 1), []);

  const value = useMemo(
    () => ({ preferences, loaded, loadFailed, saveFailed, update, reload }),
    [preferences, loaded, loadFailed, saveFailed, update, reload],
  );
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}
