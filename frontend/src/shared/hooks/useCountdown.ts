import { useCallback, useEffect, useState } from 'react';

/** Whole seconds remaining until a deadline set with start(); 0 when idle or finished. */
export function useCountdown(): { remaining: number; start: (seconds: number) => void } {
  const [deadline, setDeadline] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const start = useCallback((seconds: number) => {
    const current = Date.now();
    setNow(current);
    setDeadline(current + Math.max(0, seconds) * 1000);
  }, []);

  useEffect(() => {
    if (deadline === null) return;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= deadline) setDeadline(null);
    }, 250);
    return () => clearInterval(timer);
  }, [deadline]);

  const remaining = deadline === null ? 0 : Math.max(0, Math.ceil((deadline - now) / 1000));
  return { remaining, start };
}
