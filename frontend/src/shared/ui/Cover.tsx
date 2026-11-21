import './ui.css';
import { ProtectedImage } from './ProtectedImage';

interface CoverProps {
  /** Same-origin image URL, or null to show the initial letter. */
  src: string | null;
  title: string;
  testId?: string;
  className?: string;
  loading?: 'lazy' | 'eager';
}

export function Cover({ src, title, testId = 'cover-img', className, loading }: CoverProps) {
  return (
    <div className={`cover${className ? ` ${className}` : ''}`}>
      {src ? (
        <ProtectedImage
          className="cover__img"
          src={src}
          alt={`Capa de ${title}`}
          testId={testId}
          loading={loading}
        />
      ) : (
        <span className="cover__placeholder" aria-hidden="true">
          {title.slice(0, 1).toUpperCase()}
        </span>
      )}
    </div>
  );
}
