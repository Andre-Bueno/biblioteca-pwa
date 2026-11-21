import { useAppUpdate } from './useAppUpdate';
import './update-prompt.css';

/** "Nova versão do app disponível. Recarregar": never reloads by itself. */
export function AppUpdatePrompt() {
  const update = useAppUpdate();
  if (!update.visible) return null;

  if (update.compact) {
    return (
      <button
        type="button"
        className="btn btn--small app-update-pill"
        aria-label="Nova versão do app disponível. Toque para ver as opções."
        data-testid="app-update-pill"
        onClick={update.expand}
      >
        ↻ Atualização
      </button>
    );
  }
  return (
    <div className="app-update" role="status" data-testid="app-update">
      <span className="app-update__text">Nova versão do app disponível.</span>
      <button
        type="button"
        className="btn btn--primary btn--small"
        disabled={update.reloading}
        data-testid="app-update-reload"
        onClick={() => void update.reload()}
      >
        Recarregar
      </button>
      <button
        type="button"
        className="btn btn--small"
        data-testid="app-update-later"
        onClick={update.hide}
      >
        Depois
      </button>
    </div>
  );
}
