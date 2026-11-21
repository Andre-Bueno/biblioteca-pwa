import { useEffect, useRef, type KeyboardEvent } from 'react';
import { useSession } from '../session';
import { reloadPage } from './reload';
import { useUpdateFlow } from './useUpdateFlow';
import './system.css';

function ConfirmDialog({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => confirmRef.current?.focus(), []);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onCancel();
    }
  };
  return (
    <div className="update-confirm" data-testid="update-confirm-wrap">
      <div className="update-confirm__backdrop" onClick={onCancel} />
      <div
        className="update-confirm__box"
        role="dialog"
        aria-modal="true"
        aria-label="Confirmar atualização"
        data-testid="update-confirm"
        onKeyDown={onKeyDown}
      >
        <p>O app será reiniciado por alguns instantes. Continuar?</p>
        <div className="update-notice__actions">
          <button
            ref={confirmRef}
            type="button"
            className="btn btn--primary"
            data-testid="update-confirm-yes"
            onClick={onConfirm}
          >
            Continuar
          </button>
          <button type="button" className="btn" data-testid="update-confirm-no" onClick={onCancel}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Admin-only notice of a new app release (top of the library and of the settings). Everything
 * that comes from the network is rendered as plain text; the only link is the https release URL.
 */
export function UpdateNotice() {
  const { user } = useSession();
  const flow = useUpdateFlow();
  const { latest, info } = flow;
  if (user?.role !== 'admin' || !flow.visible || !info) return null;
  const releaseName = latest?.tag ?? flow.targetVersion ?? '';
  const working = flow.phase === 'sending' || flow.phase === 'requested';

  return (
    <section
      className="update-notice"
      role="region"
      aria-label="Atualização do app"
      data-testid="update-notice"
    >
      {flow.phase === 'done' ? (
        <>
          <p className="update-notice__message" role="status" data-testid="update-done">
            Atualizado para {flow.targetVersion}
          </p>
          <div className="update-notice__actions">
            <button
              type="button"
              className="btn btn--primary"
              data-testid="update-reload"
              onClick={reloadPage}
            >
              Recarregar
            </button>
          </div>
        </>
      ) : flow.phase === 'timeout' ? (
        <p className="update-notice__message" role="status" data-testid="update-timeout">
          A atualização continua no servidor. Recarregue a página em alguns minutos para conferir.
        </p>
      ) : working ? (
        <div role="status" data-testid="update-progress" className="update-notice__progress">
          <div className="spinner" />
          <span>
            Atualizando para {flow.targetVersion}… o app pode ficar indisponível por alguns
            instantes.
          </span>
        </div>
      ) : (
        <>
          <p className="update-notice__message" data-testid="update-message">
            Nova versão {releaseName} disponível (atual {info.current})
          </p>
          <div className="update-notice__actions">
            <button
              type="button"
              className="btn btn--small"
              aria-expanded={flow.notesOpen}
              data-testid="update-notes-toggle"
              onClick={flow.toggleNotes}
            >
              Ver novidades
            </button>
            {info.webhook_configured && (
              <button
                type="button"
                className="btn btn--primary btn--small"
                data-testid="update-now"
                onClick={flow.ask}
              >
                Atualizar agora
              </button>
            )}
            <button
              type="button"
              className="btn btn--small"
              data-testid="update-dismiss"
              onClick={flow.dismiss}
            >
              Agora não
            </button>
          </div>
          {!info.webhook_configured && (
            <p className="muted" data-testid="update-manual">
              Atualize pelo servidor: baixe a nova imagem do app e reinicie o serviço.
              {latest?.url && (
                <>
                  {' '}
                  <a
                    href={latest.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="update-manual-link"
                  >
                    Ver notas da versão
                  </a>
                </>
              )}
            </p>
          )}
          {flow.notesOpen && (
            <div data-testid="update-notes-panel">
              <pre className="update-notice__notes" data-testid="update-notes">
                {latest?.notes || 'Sem notas para esta versão.'}
              </pre>
              {latest?.url && (
                <a
                  href={latest.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="update-github"
                >
                  Abrir no GitHub
                </a>
              )}
            </div>
          )}
          {info.update.state === 'failed' && (
            <p className="alert alert--error" role="alert" data-testid="update-last-failed">
              A última tentativa de atualização falhou no servidor.
            </p>
          )}
        </>
      )}
      {flow.error && (
        <p className="alert alert--error" role="alert" data-testid="update-error">
          {flow.error}
        </p>
      )}
      {flow.phase === 'confirming' && (
        <ConfirmDialog onConfirm={flow.confirm} onCancel={flow.cancel} />
      )}
    </section>
  );
}
