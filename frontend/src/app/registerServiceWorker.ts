import { registerSW } from 'virtual:pwa-register';
import { markNeedRefresh, setUpdater } from '../shared/pwa';

/**
 * Registers the service worker in "prompt" mode: a new version waits and only the user decides
 * when to switch (the prompt in `AppUpdatePrompt`). Nothing reloads by itself.
 */
export function registerServiceWorker(enabled: boolean = import.meta.env.PROD): void {
  if (!enabled) return;
  const updateSW = registerSW({ immediate: true, onNeedRefresh: markNeedRefresh });
  setUpdater(updateSW);
}
