import { useEnrich, type EnrichPhase } from '../hooks/useEnrich';

function messageFor(phase: EnrichPhase): string | null {
  switch (phase) {
    case 'failed':
      return 'A atualização falhou. Tente novamente mais tarde.';
    case 'forbidden':
      return 'Apenas administradores podem atualizar metadados.';
    case 'rate-limited':
      return 'Muitas tentativas. Aguarde um pouco.';
    case 'error':
      return 'Não foi possível atualizar os metadados agora.';
    case 'gave-up':
      return 'A atualização continua no servidor. Volte mais tarde para ver o resultado.';
    default:
      return null;
  }
}

/** Admin-only: starts the server-side enrichment and shows a light progress summary. */
export function EnrichControl({ onFinished }: { onFinished: () => void }) {
  const enrich = useEnrich(onFinished);
  const { status, phase } = enrich;
  const message = messageFor(phase);
  const counts = status
    ? `${status.matched} ${status.matched === 1 ? 'encontrado' : 'encontrados'}, ${status.not_found} sem correspondência`
    : null;

  return (
    <div className="enrich" data-testid="enrich">
      <button
        type="button"
        className="btn"
        data-testid="enrich-button"
        disabled={enrich.running}
        onClick={() => void enrich.start()}
      >
        {enrich.running ? 'Atualizando metadados…' : 'Atualizar metadados'}
      </button>
      {(phase === 'running' || phase === 'finished') && (
        <p className="muted enrich__result" role="status" data-testid="enrich-status">
          {phase === 'finished' && 'Concluído: '}
          {counts ?? (phase === 'running' ? 'Em andamento…' : '')}
          {phase === 'running' && counts ? ' até agora' : ''}
        </p>
      )}
      {message && (
        <p
          className={`enrich__result ${phase === 'gave-up' ? 'muted' : 'alert alert--error'}`}
          role="alert"
          data-testid="enrich-message"
        >
          {message}
        </p>
      )}
    </div>
  );
}
