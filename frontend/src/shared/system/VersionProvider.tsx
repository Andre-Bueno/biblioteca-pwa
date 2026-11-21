import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSession } from '../session';
import { checkForUpdates, getVersion } from './api';
import type { VersionInfo } from './types';
import { VersionContext } from './version-context';

/** The server caches the GitHub lookup; the app only asks again after this long. */
export const VERSION_INTERVAL_MS = 30 * 60 * 1000;

/**
 * Asks `/system/version` when the signed-in app opens and then at most every 30 minutes, only
 * while the tab is visible. Failures are silent (nothing is shown, nothing is retried in a loop);
 * a 401 is handled by the api-client/session as for any other call. The answer is stored with
 * the user id it belongs to, so another user never sees it.
 */
export function VersionProvider({ children }: { children: ReactNode }) {
  const { status, user } = useSession();
  const userId = status === 'authenticated' && user ? user.id : null;
  const [remote, setRemote] = useState<{ userId: string; info: VersionInfo } | null>(null);
  const [dismissedTag, setDismissedTag] = useState<string | null>(null);

  useEffect(() => {
    if (userId === null) return undefined;
    const controller = new AbortController();
    let last = 0;
    let busy = false;
    const load = () => {
      if (busy) return;
      busy = true;
      last = Date.now();
      getVersion(controller.signal)
        .then((info) => {
          if (!controller.signal.aborted) setRemote({ userId, info });
        })
        .catch(() => undefined)
        .finally(() => {
          busy = false;
        });
    };
    const tick = () => {
      if (document.visibilityState === 'visible') load();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() - last >= VERSION_INTERVAL_MS)
        load();
    };
    load();
    const timer = setInterval(tick, VERSION_INTERVAL_MS);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      controller.abort();
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [userId]);

  const applyInfo = useCallback(
    (info: VersionInfo) => {
      if (userId !== null) setRemote({ userId, info });
    },
    [userId],
  );

  const check = useCallback(async () => {
    const info = await checkForUpdates();
    applyInfo(info);
    return info;
  }, [applyInfo]);

  const info = userId !== null && remote?.userId === userId ? remote.info : null;
  const value = useMemo(
    () => ({ info, dismissedTag, dismiss: setDismissedTag, check, applyInfo }),
    [info, dismissedTag, check, applyInfo],
  );
  return <VersionContext.Provider value={value}>{children}</VersionContext.Provider>;
}
