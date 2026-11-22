import { useEffect, useRef, useState } from 'react';
import { usePreferences } from '../../../../shared/preferences';
import type { ReaderNav } from '../../../../shared/series';
import type { ReaderData, ReaderReady } from '../../hooks/useReaderData';
import type { UnitPosition } from '../../sources';
import { ReaderGate } from '../../shell/ReaderGate';
import { ReaderShell } from '../../shell/ReaderShell';
import { useEpubReader } from '../hooks/useEpubReader';
import { EpubStrip } from './EpubStrip';
import '../epub.css';

/** Where the reader was, so a mode switch (which remounts it) resumes right there. */
interface ResumeStore {
  get: (itemId: string) => UnitPosition | null;
  set: (itemId: string, position: UnitPosition) => void;
}

function createResumeStore(): ResumeStore {
  let last: { itemId: string; position: UnitPosition } | null = null;
  return {
    get: (itemId) => (last?.itemId === itemId ? last.position : null),
    set: (itemId, position) => {
      last = { itemId, position };
    },
  };
}

function Reader({
  ready,
  nav,
  resume,
}: {
  ready: ReaderReady;
  nav: ReaderNav;
  resume: ResumeStore;
}) {
  const { item, book, source, savedLocator } = ready;
  // The saved position of the first mount; later mounts (mode switch) continue from the live one.
  const [savedPosition] = useState(() => resume.get(item.id) ?? ready.savedPosition);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const reader = useEpubReader({
    frameRef,
    item,
    book,
    nav,
    source,
    savedLocator,
    savedPosition,
  });
  const { position } = reader;
  useEffect(() => {
    resume.set(item.id, position);
  }, [resume, item.id, position]);
  return (
    <div className="epub" data-testid="epub-reader">
      {/*
        The book lives ONLY here: the server sends a sanitized, complete HTML document and the
        sandbox has no allow-scripts / allow-popups / allow-forms / allow-top-navigation.
        allow-same-origin is what lets the app read the scroll position and clicks.
      */}
      {reader.vertical ? (
        <EpubStrip reader={reader} />
      ) : (
        <iframe
          key={reader.frameKey}
          ref={frameRef}
          className="epub-frame"
          title={`Livro ${reader.title}, capítulo ${reader.chapter + 1} de ${reader.count}`}
          src={reader.src}
          sandbox="allow-same-origin"
          referrerPolicy="no-referrer"
          onLoad={reader.onFrameLoad}
          data-testid="epub-frame"
        />
      )}
      {reader.loading && (
        <div className="epub-loading" role="status" data-testid="chapter-loading">
          <div className="spinner" />
          <span className="muted">Carregando capítulo…</span>
        </div>
      )}
      {reader.frameFailed && (
        <div className="epub-failed" role="alert" data-testid="chapter-error">
          <p>Não foi possível carregar este capítulo.</p>
          <button type="button" className="btn" data-testid="chapter-retry" onClick={reader.retry}>
            Tentar novamente
          </button>
        </div>
      )}
      <ReaderShell {...reader.shell} />
    </div>
  );
}

interface EpubReaderPageProps {
  data: ReaderData;
  nav: ReaderNav;
  retry: () => void;
}

/** Route screen for a source made of HTML chapters (`/ler/:itemId` when the item is a book). */
export function EpubReaderPage({ data, nav, retry }: EpubReaderPageProps) {
  // The first src already uses the saved theme and size; the reading direction picks the mode.
  const { preferences } = usePreferences();
  const vertical = preferences.reading_direction === 'vertical';
  const [resume] = useState(createResumeStore);
  return (
    <ReaderGate data={data} retry={retry}>
      {(ready) => (
        <Reader
          key={`${ready.item.id}:${vertical ? 'v' : 'p'}`}
          ready={ready}
          nav={nav}
          resume={resume}
        />
      )}
    </ReaderGate>
  );
}
