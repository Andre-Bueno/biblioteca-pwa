import { useEffect, useState } from 'react';
import { listContinue, type ContinueEntry } from '../../../shared/progress';

/** "Continue reading" shelf. A failure just hides the shelf: it must not block the library. */
export function useContinueReading(limit = 12): ContinueEntry[] {
  const [entries, setEntries] = useState<ContinueEntry[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    listContinue(limit, controller.signal)
      .then(setEntries)
      .catch(() => undefined);
    return () => controller.abort();
  }, [limit]);

  return entries;
}
