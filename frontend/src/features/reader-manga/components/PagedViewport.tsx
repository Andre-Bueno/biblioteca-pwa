import { pageUrl } from '../../../shared/items';
import { ProtectedImage } from '../../../shared/ui';
import { useViewportGestures } from '../hooks/useViewportGestures';
import type { ReaderState } from '../hooks/useReaderState';

export function PagedViewport({ reader }: { reader: ReaderState }) {
  const gestures = useViewportGestures({
    mode: reader.mode,
    zoomed: reader.zoomed,
    onStep: reader.step,
    onCenterTap: reader.toggleControls,
    onDoubleTap: reader.toggleZoom,
  });

  return (
    <div
      className={`viewport${reader.zoomed ? ' viewport--zoomed' : ''}`}
      data-testid="reader-viewport"
      data-mode={reader.mode}
      data-zoomed={reader.zoomed}
      tabIndex={0}
      role="group"
      aria-label={`Página ${reader.page + 1} de ${reader.pageCount}. Setas mudam de página; Enter ou M mostra e oculta os controles.`}
      onKeyDown={(event) => {
        if (event.key === 'Enter' && event.target === event.currentTarget) reader.toggleControls();
      }}
      {...gestures}
    >
      <ProtectedImage
        key={reader.page}
        className="viewport__img"
        loading="eager"
        src={pageUrl(reader.item.id, reader.page)}
        alt={`Página ${reader.page + 1} de ${reader.pageCount}`}
        testId="reader-page-img"
      />
      {/* Focusable equivalents of the touch zones for keyboard and screen-reader users. */}
      <button
        type="button"
        className="sr-only sr-only--focusable"
        data-testid="zone-prev"
        onPointerDown={(event) => event.stopPropagation()}
        onPointerUp={(event) => event.stopPropagation()}
        onClick={() => reader.step('prev')}
      >
        Página anterior
      </button>
      <button
        type="button"
        className="sr-only sr-only--focusable"
        data-testid="zone-next"
        onPointerDown={(event) => event.stopPropagation()}
        onPointerUp={(event) => event.stopPropagation()}
        onClick={() => reader.step('next')}
      >
        Próxima página
      </button>
    </div>
  );
}
