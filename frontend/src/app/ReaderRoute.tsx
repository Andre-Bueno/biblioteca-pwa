import { EpubReaderPage } from '../features/reader-epub';
import { MangaReaderPage } from '../features/reader-manga';
import { useReaderKind } from './useReaderKind';

/** `/ler/:itemId`: manga opens the manga reader, a book opens the EPUB reader. */
export function ReaderRoute() {
  const { kind, itemState, retryItem } = useReaderKind();
  return kind === 'book' ? (
    <EpubReaderPage itemState={itemState} retryItem={retryItem} />
  ) : (
    <MangaReaderPage itemState={itemState} retryItem={retryItem} />
  );
}
