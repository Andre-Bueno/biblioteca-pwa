import type { ReaderNav } from '../../../../shared/series';
import type { ReaderData, ReaderReady } from '../../hooks/useReaderData';
import { ReaderGate } from '../../shell/ReaderGate';
import { ReaderShell } from '../../shell/ReaderShell';
import { useReaderState } from '../hooks/useReaderState';
import { PagedViewport } from './PagedViewport';
import { VerticalViewport } from './VerticalViewport';
import '../reader.css';

function Reader({ ready, nav }: { ready: ReaderReady; nav: ReaderNav }) {
  const { item, source, savedLocator, savedPosition } = ready;
  const reader = useReaderState({ item, source, nav, savedLocator, savedPosition });
  return (
    <div className="reader" data-testid="reader" data-mode={reader.mode}>
      {reader.mode === 'vertical' ? (
        <VerticalViewport reader={reader} />
      ) : (
        <PagedViewport reader={reader} />
      )}
      <ReaderShell {...reader.shell} />
    </div>
  );
}

interface MangaReaderPageProps {
  data: ReaderData;
  nav: ReaderNav;
  retry: () => void;
}

/** Route screen for a source made of image pages (`/ler/:itemId` when the item is not a book). */
export function MangaReaderPage({ data, nav, retry }: MangaReaderPageProps) {
  return (
    <ReaderGate data={data} retry={retry}>
      {(ready) => <Reader key={ready.item.id} ready={ready} nav={nav} />}
    </ReaderGate>
  );
}
