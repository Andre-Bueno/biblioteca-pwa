import './ui.css';
import { useImageRecovery } from './useImageRecovery';

interface ProtectedImageProps {
  src: string;
  alt: string;
  className?: string;
  loading?: 'lazy' | 'eager';
  testId?: string;
  /** Called after the image finished loading (e.g. to re-position a scrolled strip). */
  onLoaded?: () => void;
}

/** Same-origin image (cookies travel with it) with placeholder, one recovery and a retry button. */
export function ProtectedImage({
  src,
  alt,
  className,
  loading = 'lazy',
  testId,
  onLoaded,
}: ProtectedImageProps) {
  const { state, attempt, onLoad, onError, retry } = useImageRecovery();

  if (state === 'failed') {
    return (
      <span className={`img-fallback ${className ?? ''}`} role="img" aria-label={alt}>
        <span>Imagem indisponível</span>
        <button type="button" className="btn btn--small" onClick={retry}>
          Tentar novamente
        </button>
      </span>
    );
  }
  return (
    <img
      key={attempt}
      className={className}
      src={src}
      alt={alt}
      loading={loading}
      decoding="async"
      draggable={false}
      data-state={state}
      data-testid={testId}
      onLoad={() => {
        onLoad();
        onLoaded?.();
      }}
      onError={onError}
    />
  );
}
