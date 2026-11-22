import { useParams } from 'react-router-dom';
import { useReaderNav } from '../shared/series';
import { EpubReaderPage, MangaReaderPage, useReaderData } from '../features/reader';
import { useReaderKind } from './useReaderKind';

/** `/ler/:itemId`: the data hook picks the source; HTML chapters open the book reader. */
export function ReaderRoute() {
  const { itemId = '' } = useParams();
  const { data, retry } = useReaderData(itemId);
  const kind = useReaderKind(data);
  // Here so the series data survives moving between chapters (the readers remount per item).
  const nav = useReaderNav(data.status === 'ready' ? data.item : null);
  return kind === 'chapters' ? (
    <EpubReaderPage data={data} nav={nav} retry={retry} />
  ) : (
    <MangaReaderPage data={data} nav={nav} retry={retry} />
  );
}
