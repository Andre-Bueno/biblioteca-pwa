import { useState, type FormEvent } from 'react';
import { safeHttpsUrl, type MetadataState, type SeriesDetail } from '../../../shared/series';
import {
  DESCRIPTION_MAX,
  TITLE_MAX,
  useMetadataAdmin,
  type CandidatesState,
} from '../hooks/useMetadataAdmin';

export const METADATA_STATE_LABEL: Record<MetadataState, string> = {
  none: 'Sem metadados',
  matched: 'Correspondência automática',
  manual: 'Editado manualmente',
  not_found: 'Não encontrado',
};

export function providerLabel(provider: string): string {
  switch (provider) {
    case 'mangadex':
      return 'MangaDex';
    case 'anilist':
      return 'AniList';
    case 'wikipedia':
      return 'Wikipédia';
    case 'googlebooks':
      return 'Google Livros';
    default:
      return provider;
  }
}

const EXCERPT = 200;
const excerpt = (text: string) => (text.length > EXCERPT ? `${text.slice(0, EXCERPT)}…` : text);

function Candidates({
  state,
  busy,
  onChoose,
  retryIn,
}: {
  state: CandidatesState;
  busy: boolean;
  onChoose: (index: number) => void;
  retryIn: number;
}) {
  if (state.status === 'loading') {
    return (
      <div className="series__state" role="status" data-testid="candidates-loading">
        <div className="spinner" />
        <span className="muted">Buscando nas fontes públicas…</span>
      </div>
    );
  }
  if (state.status === 'error') {
    return (
      <p className="alert alert--error" role="alert" data-testid="candidates-error">
        Não foi possível buscar agora. Tente novamente.
      </p>
    );
  }
  if (state.status === 'rate-limited') {
    return (
      <p className="alert" role="alert" data-testid="candidates-rate-limit">
        Muitas buscas seguidas.{' '}
        {retryIn > 0 ? `Tente de novo em ${retryIn} s.` : 'Você já pode tentar de novo.'}
      </p>
    );
  }
  if (state.status === 'ready') {
    if (state.items.length === 0) {
      return (
        <p className="muted" data-testid="candidates-empty">
          Nenhum resultado para esta busca.
        </p>
      );
    }
    return (
      <ul className="candidates" data-testid="candidates-list">
        {state.items.map((candidate, index) => {
          const link = safeHttpsUrl(candidate.url);
          return (
            <li
              key={`${candidate.provider}:${candidate.external_id}`}
              className="candidate"
              data-testid="candidate"
            >
              <div className="candidate__body">
                <strong className="candidate__title">{candidate.title}</strong>
                <span className="muted candidate__meta">
                  {candidate.year ? `${candidate.year} · ` : ''}
                  {link ? (
                    <a href={link} target="_blank" rel="noopener noreferrer">
                      {providerLabel(candidate.provider)}
                    </a>
                  ) : (
                    providerLabel(candidate.provider)
                  )}
                  {!candidate.cover_available && (
                    <span className="badge" data-testid="candidate-text-only">
                      só descrição
                    </span>
                  )}
                </span>
                {candidate.description && (
                  <span className="candidate__text">{excerpt(candidate.description)}</span>
                )}
              </div>
              <button
                type="button"
                className="btn btn--small"
                data-testid="candidate-use"
                disabled={busy}
                onClick={() => onChoose(index)}
              >
                Usar este
              </button>
            </li>
          );
        })}
      </ul>
    );
  }
  return null;
}

/** Admin-only panel (collapsed by default). The candidates API is only called on explicit search. */
export function MetadataPanel({
  series,
  onChanged,
}: {
  series: SeriesDetail;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(series.title);
  const [title, setTitle] = useState(series.title);
  const [description, setDescription] = useState(series.description ?? '');
  const [confirming, setConfirming] = useState(false);
  // When the reloaded detail brings new text, the form follows it (adjust state during render).
  const [seen, setSeen] = useState({ title: series.title, description: series.description });
  if (seen.title !== series.title || seen.description !== series.description) {
    setSeen({ title: series.title, description: series.description });
    setTitle(series.title);
    setDescription(series.description ?? '');
  }
  const admin = useMetadataAdmin(series.id, onChanged);

  const searching = admin.candidates.status === 'loading';
  const searchBlocked = searching || admin.busy || admin.retryIn > 0 || query.trim() === '';
  const titleOk = title.trim() !== '' && title.length <= TITLE_MAX;
  const descriptionOk = description.length <= DESCRIPTION_MAX;

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    void admin.search(query);
  };
  const submitText = (event: FormEvent) => {
    event.preventDefault();
    if (titleOk && descriptionOk) void admin.saveText(title, description);
  };
  const choose = (index: number) => {
    if (admin.candidates.status !== 'ready') return;
    const candidate = admin.candidates.items.at(index);
    if (!candidate) return;
    void admin.choose(candidate);
  };
  const confirmRemove = () => {
    setConfirming(false);
    void admin.remove();
  };

  return (
    <section className="meta-panel" aria-label="Metadados (administração)" data-testid="meta-panel">
      <div className="meta-panel__head">
        <span className="badge" data-testid="metadata-state">
          {METADATA_STATE_LABEL[series.metadata_state]}
        </span>
        <button
          type="button"
          className="btn btn--small"
          aria-expanded={open}
          aria-controls="meta-panel-body"
          data-testid="meta-toggle"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? 'Fechar metadados' : 'Gerenciar metadados'}
        </button>
      </div>

      {open && (
        <div id="meta-panel-body" className="meta-panel__body" data-testid="meta-body">
          {admin.feedback && (
            <p
              className={`alert alert--${admin.feedback.kind}`}
              role={admin.feedback.kind === 'error' ? 'alert' : 'status'}
              data-testid="meta-feedback"
            >
              {admin.feedback.text}
            </p>
          )}

          <form className="meta-form" onSubmit={submitSearch}>
            <h3 className="meta-form__title">Buscar metadados</h3>
            <label className="field">
              <span className="field__label">Título para buscar</span>
              <input
                className="input"
                type="search"
                maxLength={TITLE_MAX}
                autoComplete="off"
                data-testid="meta-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <button
              type="submit"
              className="btn"
              data-testid="meta-search"
              disabled={searchBlocked}
            >
              {searching ? 'Buscando…' : 'Buscar'}
            </button>
          </form>
          <Candidates
            state={admin.candidates}
            busy={admin.busy}
            onChoose={choose}
            retryIn={admin.retryIn}
          />

          <form className="meta-form" onSubmit={submitText}>
            <h3 className="meta-form__title">Editar texto</h3>
            <label className="field">
              <span className="field__label">Título</span>
              <input
                className="input"
                type="text"
                maxLength={TITLE_MAX}
                data-testid="meta-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
              <span className="muted meta-form__count" data-testid="meta-title-count">
                {title.length}/{TITLE_MAX}
              </span>
            </label>
            <label className="field">
              <span className="field__label">Descrição</span>
              <textarea
                className="input meta-form__textarea"
                rows={6}
                maxLength={DESCRIPTION_MAX}
                data-testid="meta-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <span className="muted meta-form__count" data-testid="meta-description-count">
                {description.length}/{DESCRIPTION_MAX}
              </span>
            </label>
            <button
              type="submit"
              className="btn btn--primary"
              data-testid="meta-save"
              disabled={admin.busy || !titleOk || !descriptionOk}
            >
              Salvar
            </button>
          </form>

          <div className="meta-form">
            <h3 className="meta-form__title">Remover metadados</h3>
            {confirming ? (
              <div className="meta-confirm" role="alertdialog" aria-label="Confirmar remoção">
                <p>Remover descrição, fonte e capa obtidas? A série volta ao estado original.</p>
                <button
                  type="button"
                  className="btn btn--danger"
                  data-testid="meta-remove-confirm"
                  disabled={admin.busy}
                  onClick={confirmRemove}
                >
                  Sim, remover
                </button>
                <button
                  type="button"
                  className="btn"
                  data-testid="meta-remove-cancel"
                  onClick={() => setConfirming(false)}
                >
                  Cancelar
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="btn btn--danger"
                data-testid="meta-remove"
                disabled={admin.busy}
                onClick={() => setConfirming(true)}
              >
                Remover metadados
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
