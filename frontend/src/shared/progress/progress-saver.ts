import type { SaveStatus } from './types';

export interface ProgressSaverOptions {
  /** Performs the network save. keepalive=true when the page is going away. */
  save: (locator: number, options: { keepalive: boolean }) => Promise<unknown>;
  delayMs?: number;
  retryMs?: number;
  onStatus?: (status: SaveStatus) => void;
}

export interface ProgressSaver {
  /** Records a new locator; the save happens after the debounce. */
  report(locator: number): void;
  /**
   * Sends the pending locator now (page hidden / leaving). If a save is already in flight, it is
   * NOT raced: the newest value goes out right after it, with keepalive.
   */
  flush(keepalive?: boolean): Promise<void>;
  /** Tells the saver which value the server already has (so it is not re-sent). */
  setBaseline(locator: number | null): void;
  /** Stops timers and new reports. A save/flush already requested still finishes. */
  dispose(): void;
}

/**
 * Debounced, failure-tolerant progress writer. Framework-free so the timing rules are testable.
 *
 * There is never more than ONE save in flight, so writes reach the server in order and the
 * latest locator always wins (older pending values are simply replaced). A failed save keeps the
 * locator pending and retries later; reading is never interrupted.
 */
export function createProgressSaver(options: ProgressSaverOptions): ProgressSaver {
  const delayMs = options.delayMs ?? 800;
  const retryMs = options.retryMs ?? 5000;
  let pending: number | null = null;
  let lastSaved: number | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let running: Promise<void> | null = null;
  let urgent = false; // next save must use keepalive (the page is going away)
  let disposed = false;

  const clear = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
  const schedule = (ms: number) => {
    clear();
    timer = setTimeout(() => void flush(false), ms);
  };

  async function drain(): Promise<void> {
    try {
      while (pending !== null) {
        const locator = pending;
        pending = null;
        if (locator === lastSaved) continue;
        const keepalive = urgent;
        urgent = false;
        options.onStatus?.('saving');
        try {
          await options.save(locator, { keepalive });
          lastSaved = locator;
          options.onStatus?.('idle');
        } catch {
          if (pending === null) pending = locator; // a newer value replaces it, else retry it
          options.onStatus?.('error');
          if (!disposed) schedule(retryMs);
          return;
        }
      }
    } finally {
      urgent = false;
    }
  }

  function flush(keepalive = false): Promise<void> {
    clear();
    if (keepalive) urgent = true;
    if (running) return running; // the running loop sends the newest value next
    running = drain().finally(() => {
      running = null;
    });
    return running;
  }

  return {
    report(locator) {
      if (disposed) return;
      if (locator === lastSaved && pending === null) return;
      pending = locator;
      schedule(delayMs);
    },
    flush,
    setBaseline(locator) {
      lastSaved = locator;
    },
    dispose() {
      disposed = true;
      clear();
    },
  };
}
