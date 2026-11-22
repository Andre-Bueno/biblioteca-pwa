import { useState } from 'react';
import type { ReaderData, SourceKind } from '../features/reader';

/**
 * Picks the reader screen from the source the data hook chose for the item. The last known kind
 * is kept while the next item loads, so moving between chapters of the same kind keeps the reader
 * (and its series data) mounted. Until the first answer, and for errors / unsupported types, the
 * page reader renders: it already shows loading and error states.
 */
export function useReaderKind(data: ReaderData): SourceKind {
  const [kind, setKind] = useState<SourceKind>('pages');
  if (data.status === 'ready') {
    if (data.source.kind !== kind) setKind(data.source.kind);
    return data.source.kind;
  }
  return kind;
}
