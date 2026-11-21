type Flusher = () => Promise<void>;

const flushers = new Set<Flusher>();

/** Readers register their saver here so the app can flush pending progress before a reload. */
export function registerProgressFlusher(flusher: Flusher): () => void {
  flushers.add(flusher);
  return () => flushers.delete(flusher);
}

/**
 * Sends every pending reading position now. Never rejects and never waits longer than
 * `timeoutMs`: a reload must not hang on a slow or failing server.
 */
export async function flushAllProgress(timeoutMs = 2000): Promise<void> {
  const all = Promise.allSettled([...flushers].map((flusher) => flusher()));
  await Promise.race([all, new Promise<void>((resolve) => setTimeout(resolve, timeoutMs))]);
}
