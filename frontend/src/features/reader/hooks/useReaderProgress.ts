import { useCallback, useEffect } from 'react';
import { useProgressSaver } from '../../../shared/progress';
import type { ReaderSource, UnitPosition } from '../sources';

/**
 * Progress saving shared by every reader: the server's value is the baseline (not re-sent), a
 * first visit registers the opening position (so the item shows up in "continue reading") and
 * every later position is encoded by the source codec before it goes to the saver.
 */
export function useReaderProgress(
  itemId: string,
  source: ReaderSource,
  savedLocator: number | null,
  initial: UnitPosition,
) {
  const saver = useProgressSaver(itemId);
  const { setBaseline, report } = saver;
  const { codec, unitCount } = source;

  useEffect(() => {
    setBaseline(savedLocator);
    if (savedLocator === null && unitCount > 0) report(codec.encode(initial.unit, initial.bp));
  }, [setBaseline, report, codec, savedLocator, unitCount, initial]);

  const reportPosition = useCallback(
    (unit: number, bp = 0) => report(codec.encode(unit, bp)),
    [report, codec],
  );

  return { reportPosition, saveStatus: saver.status };
}
