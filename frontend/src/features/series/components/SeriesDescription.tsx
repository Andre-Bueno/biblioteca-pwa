import { useState } from 'react';
import { safeHttpsUrl, type SeriesDetail } from '../../../shared/series';

export const DESCRIPTION_COLLAPSE_AT = 280;

function langLabel(lang: string): string {
  if (lang === 'en') return 'em inglês';
  if (lang === 'pt') return 'em português de Portugal';
  return lang;
}

const isWikipedia = (name: string) => name.trim().toLowerCase().startsWith('wikip');

/** Origin badges and source attribution. Everything is plain text; links only for https. */
function DescriptionCredits({ series }: { series: SeriesDetail }) {
  const origin = series.description_origin ?? null;
  const source = series.description_source ?? null;
  if (!origin && !source) return null;
  const url = safeHttpsUrl(source?.url);
  return (
    <div className="series__credits muted" data-testid="description-credits">
      {origin === 'translated' && (
        <span data-testid="description-origin">
          <span className="badge">tradução automática</span> a partir do original em inglês
        </span>
      )}
      {origin === 'manual' && (
        <span className="badge" data-testid="description-origin">
          editada manualmente
        </span>
      )}
      {source && (
        <span data-testid="description-source">
          Descrição:{' '}
          {url ? (
            <a href={url} target="_blank" rel="noopener noreferrer">
              {source.name}
            </a>
          ) : (
            source.name
          )}
          {isWikipedia(source.name) && <span data-testid="description-license"> · CC BY-SA</span>}
        </span>
      )}
    </div>
  );
}

export function SeriesDescription({ series }: { series: SeriesDetail }) {
  const [expanded, setExpanded] = useState(false);
  const text = series.description;
  if (!text) return null;
  const lang = series.description_lang;
  const badge = lang && lang !== 'pt-br' ? langLabel(lang) : null;
  const long = text.length > DESCRIPTION_COLLAPSE_AT;
  const collapsed = long && !expanded;

  return (
    <section aria-labelledby="about-title" className="series__about">
      <h2 id="about-title" className="series__section-title">
        Sobre
        {badge && (
          <span className="badge" data-testid="description-lang">
            {badge}
          </span>
        )}
      </h2>
      {/* Plain text node: React escapes it, so hostile HTML in the description stays inert. */}
      <p
        className={`series__description${collapsed ? ' series__description--clamped' : ''}`}
        data-testid="series-description"
        data-collapsed={collapsed ? 'true' : 'false'}
      >
        {text}
      </p>
      {long && (
        <button
          type="button"
          className="btn btn--small series__toggle"
          aria-expanded={expanded}
          data-testid="description-toggle"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Ler menos' : 'Ler mais'}
        </button>
      )}
      <DescriptionCredits series={series} />
    </section>
  );
}
