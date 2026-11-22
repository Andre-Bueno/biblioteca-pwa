import { useCallback, useEffect, useMemo } from 'react';
import type { ReadingDirection } from '../../../shared/preferences';
import type { ReaderSource } from '../sources';
import { createInputContext, keyIntent, type InputContext, type ReaderIntent } from './intents';

interface Params {
  source: Pick<ReaderSource, 'kind' | 'capabilities'>;
  mode: ReadingDirection;
  zoomed?: boolean;
  /** Keys of the chrome (menu, escape...) go first; true means it consumed the key. */
  handleChromeKey: (event: KeyboardEvent) => boolean;
  onIntent: (intent: ReaderIntent) => void;
}

/**
 * Single keyboard entry of every reader: maps the key to an intent by direction and source and
 * hands it over. Listens on the window; `handleKey` is also what an iframe document forwards.
 */
export function useReaderInput({
  source,
  mode,
  zoomed = false,
  handleChromeKey,
  onIntent,
}: Params): { input: InputContext; handleKey: (event: KeyboardEvent) => void } {
  const input = useMemo(() => createInputContext(source, mode, zoomed), [source, mode, zoomed]);

  const handleKey = useCallback(
    (event: KeyboardEvent) => {
      if (handleChromeKey(event)) return;
      const intent = keyIntent(event.key, input);
      if (!intent) return;
      event.preventDefault();
      onIntent(intent);
    },
    [handleChromeKey, input, onIntent],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  return { input, handleKey };
}
