import { useEffect, useRef, useState } from 'react';
import type { EpubReaderState } from '../hooks/useEpubReader';
import type { EpubStrip as StripApi } from '../hooks/useEpubStrip';

interface FrameProps {
  index: number;
  total: number;
  title: string;
  src: string;
  attachFrame: StripApi['attachFrame'];
}

/** Lives only while its chapter is inside the mounted window, so its state resets by itself. */
function StripFrame({ index, total, title, src, attachFrame }: FrameProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const disposeRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>('loading');
  const [nonce, setNonce] = useState(0);

  useEffect(
    () => () => {
      disposeRef.current?.(); // the iframe left the window: stop watching its document
      disposeRef.current = null;
    },
    [],
  );

  const handleLoad = () => {
    const frame = frameRef.current;
    if (!frame) return;
    disposeRef.current?.();
    const result = attachFrame(index, frame);
    disposeRef.current = result.dispose;
    setStatus(result.ok ? 'ready' : 'failed');
  };

  return (
    <>
      <iframe
        key={nonce}
        ref={frameRef}
        className="epub-strip__frame"
        title={`${title}, capítulo ${index + 1} de ${total}`}
        src={src}
        sandbox="allow-same-origin"
        referrerPolicy="no-referrer"
        scrolling="no"
        onLoad={handleLoad}
        data-testid="strip-frame"
      />
      {status === 'loading' && (
        <div className="epub-strip__note" role="status">
          <div className="spinner" />
        </div>
      )}
      {status === 'failed' && (
        <div className="epub-strip__note" role="alert" data-testid="chapter-error">
          <p>Não foi possível carregar este capítulo.</p>
          <button
            type="button"
            className="btn"
            data-testid="chapter-retry"
            onClick={() => {
              setStatus('loading');
              setNonce((value) => value + 1);
            }}
          >
            Tentar novamente
          </button>
        </div>
      )}
    </>
  );
}

/** Continuous vertical reading (reading direction "Vertical"): chapters stacked, loaded on demand. */
export function EpubStrip({ reader }: { reader: EpubReaderState }) {
  const { containerRef, mounted, heightOf, attachFrame } = reader.strip;
  const { count, chapterUrl } = reader;
  const title = reader.book.title || reader.item.title;
  return (
    <div
      ref={containerRef}
      className="epub-strip"
      data-testid="epub-strip"
      data-mode="vertical"
      role="group"
      aria-label={`Leitura contínua, capítulo ${reader.chapter + 1} de ${count}`}
    >
      {Array.from({ length: count }, (_, index) => {
        const live = index >= mounted.from && index <= mounted.to;
        return (
          <div
            key={index}
            className="epub-strip__chapter"
            data-chapter={index}
            data-mounted={live}
            data-testid="strip-chapter"
            style={{ height: heightOf(index) }}
          >
            {live && (
              <StripFrame
                index={index}
                total={count}
                title={title}
                src={chapterUrl(index)}
                attachFrame={attachFrame}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
