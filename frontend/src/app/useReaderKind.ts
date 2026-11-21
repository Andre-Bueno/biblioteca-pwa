import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useItem, type ItemState } from '../shared/items';

export type ReaderKind = 'manga' | 'book';

/**
 * Picks the reader for `/ler/:itemId` from the item type. The item is loaded ONCE here and passed
 * down. The last known kind is kept while the next item loads, so moving between chapters of the
 * same kind keeps the reader (and its series data) mounted. Until the first answer, and for
 * errors / unknown types, the manga reader renders: it already shows loading and error states.
 */
export function useReaderKind(): { kind: ReaderKind; itemState: ItemState; retryItem: () => void } {
  const { itemId = '' } = useParams();
  const { state, retry } = useItem(itemId);
  const [kind, setKind] = useState<ReaderKind>('manga');
  if (state.status === 'ready') {
    const next: ReaderKind = state.item.type === 'book' ? 'book' : 'manga';
    if (next !== kind) setKind(next);
    return { kind: next, itemState: state, retryItem: retry };
  }
  return { kind, itemState: state, retryItem: retry };
}
