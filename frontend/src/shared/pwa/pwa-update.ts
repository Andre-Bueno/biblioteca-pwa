/**
 * Tiny external store for "a new service worker is waiting". The registration code (in app/)
 * feeds it; the prompt reads it. Nothing here reloads the page by itself.
 */
type Updater = (reloadPage?: boolean) => Promise<void>;

let needRefresh = false;
let updater: Updater | null = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((listener) => listener());

export function setUpdater(next: Updater): void {
  updater = next;
}

export function markNeedRefresh(): void {
  needRefresh = true;
  emit();
}

export function resetPwaUpdate(): void {
  needRefresh = false;
  updater = null;
  emit();
}

export function subscribePwaUpdate(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getNeedRefresh(): boolean {
  return needRefresh;
}

/** Activates the waiting worker and reloads (the caller flushes reading progress first). */
export async function applyPwaUpdate(): Promise<void> {
  await updater?.(true);
}
