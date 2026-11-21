import { useCallback, useState, useSyncExternalStore } from 'react';
import { useLocation } from 'react-router-dom';
import { flushAllProgress } from '../shared/progress';
import { applyPwaUpdate, getNeedRefresh, subscribePwaUpdate } from '../shared/pwa';

/**
 * State of the "new app version is waiting" prompt. Reloading is always the user's choice, and
 * the pending reading position is sent first (never waiting more than ~2 s).
 */
export function useAppUpdate() {
  const needRefresh = useSyncExternalStore(subscribePwaUpdate, getNeedRefresh);
  const { pathname } = useLocation();
  const [hidden, setHidden] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [reloading, setReloading] = useState(false);

  const reload = useCallback(async () => {
    setReloading(true);
    await flushAllProgress();
    try {
      await applyPwaUpdate();
    } finally {
      setReloading(false);
    }
  }, []);

  return {
    visible: needRefresh && !hidden,
    /** Inside a reader only a small indicator shows; the user opens it if they want. */
    compact: pathname.startsWith('/ler/') && !expanded,
    reloading,
    expand: useCallback(() => setExpanded(true), []),
    hide: useCallback(() => setHidden(true), []),
    reload,
  };
}
