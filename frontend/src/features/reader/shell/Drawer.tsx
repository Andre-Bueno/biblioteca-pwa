import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react';

const FOCUSABLE = 'button:not([disabled]), a[href], input:not([disabled]), [tabindex="0"]';

interface DrawerProps {
  title: string;
  testId: string;
  onClose: () => void;
  children: ReactNode;
}

/**
 * Side panel (dialog): takes the focus when it opens, keeps Tab inside, closes with Esc or a tap
 * on the backdrop, and gives the focus back to the control that opened it.
 */
export function Drawer({ title, testId, onClose, children }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    ref.current?.focus();
    return () => opener?.focus();
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== 'Tab' || !ref.current) return;
    const items = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) return;
    if (
      event.shiftKey &&
      (document.activeElement === first || document.activeElement === ref.current)
    ) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <>
      <div className="reader-backdrop" onClick={onClose} data-testid={`${testId}-backdrop`} />
      <div
        ref={ref}
        className="reader-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        data-testid={testId}
        onKeyDown={onKeyDown}
      >
        <header className="reader-drawer__header">
          <h2 className="reader-drawer__title">{title}</h2>
          <button
            type="button"
            className="btn"
            aria-label={`Fechar ${title.toLowerCase()}`}
            data-testid={`${testId}-close`}
            onClick={onClose}
          >
            ✕
          </button>
        </header>
        {children}
      </div>
    </>
  );
}
