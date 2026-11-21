import { useCallback, useRef, useState } from 'react';
import { pageUrl } from '../../../shared/items';
import { ProtectedImage } from '../../../shared/ui';
import { STRIP_WINDOW, useVerticalStrip } from '../hooks/useVerticalStrip';
import { useViewportGestures } from '../hooks/useViewportGestures';
import type { ReaderState } from '../hooks/useReaderState';

const noop = () => undefined;

interface StripPageProps {
  index: number;
  total: number;
  itemId: string;
  mounted: boolean;
  /** Last measured height, kept so unmounted pages do not collapse and shift the scroll. */
  reservedHeight: number | undefined;
  onLoaded: (index: number, height: number) => void;
}

function StripPage({ index, total, itemId, mounted, reservedHeight, onLoaded }: StripPageProps) {
  const ref = useRef<HTMLDivElement>(null);

  const handleLoaded = useCallback(() => {
    // The wrapper is as tall as its loaded image: remember it for when the page is unmounted.
    const image = ref.current?.querySelector('img');
    onLoaded(index, image?.offsetHeight ?? 0);
  }, [index, onLoaded]);

  return (
    <div
      ref={ref}
      className="strip__page"
      data-page={index}
      data-mounted={mounted}
      data-testid="strip-page"
      // Only unmounted pages reserve their old height; mounted ones size themselves.
      style={!mounted && reservedHeight ? { minHeight: reservedHeight } : undefined}
    >
      {mounted && (
        <ProtectedImage
          className="strip__img"
          loading="lazy"
          src={pageUrl(itemId, index)}
          alt={`Página ${index + 1} de ${total}`}
          onLoaded={handleLoaded}
        />
      )}
    </div>
  );
}

export function VerticalViewport({ reader }: { reader: ReaderState }) {
  // Where this strip opened: progress is never lowered below it without a user gesture.
  const [startPage] = useState(reader.page);
  const { ref, heightOf, onPageLoaded } = useVerticalStrip({
    pageCount: reader.pageCount,
    initialPage: startPage,
    jump: reader.jump,
    onVisiblePage: reader.onVisiblePage,
  });
  const gestures = useViewportGestures({
    mode: 'vertical',
    zoomed: false,
    onStep: noop,
    onCenterTap: reader.toggleControls,
    onDoubleTap: noop,
  });

  return (
    <div
      ref={ref}
      className="strip"
      data-testid="reader-strip"
      data-mode="vertical"
      tabIndex={0}
      role="group"
      aria-label={`Leitura contínua, página ${reader.page + 1} de ${reader.pageCount}. Enter mostra ou oculta os controles.`}
      onKeyDown={(event) => {
        if (event.key === 'Enter' && event.target === event.currentTarget) reader.toggleControls();
      }}
      {...gestures}
    >
      {Array.from({ length: reader.pageCount }, (_, index) => (
        <StripPage
          key={index}
          index={index}
          total={reader.pageCount}
          itemId={reader.item.id}
          mounted={Math.abs(index - reader.page) <= STRIP_WINDOW}
          reservedHeight={heightOf(index)}
          onLoaded={onPageLoaded}
        />
      ))}
    </div>
  );
}
