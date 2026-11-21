import { useState, type FormEvent } from 'react';
import type { Chapter } from '../../../shared/series';
import { useChapterList } from '../hooks/useChapterList';
import { ChapterRow } from './ChapterRow';

const INVALID_MESSAGE = 'Digite um número de capítulo válido.';
const NOTFOUND_MESSAGE = 'Capítulo não encontrado nesta série.';

export function ChapterList({ chapters, seriesId }: { chapters: Chapter[]; seriesId: string }) {
  const list = useChapterList(chapters);
  const [input, setInput] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const result = list.goToNumber(input);
    if (result === 'found') setProblem(null);
    else setProblem(result === 'invalid' ? INVALID_MESSAGE : NOTFOUND_MESSAGE);
  };

  return (
    <section aria-labelledby="chapters-title" data-testid="chapter-section">
      <h2 id="chapters-title" className="series__section-title">
        Capítulos
      </h2>
      <form className="goto" onSubmit={submit} data-testid="goto-form">
        <input
          className="input"
          type="text"
          inputMode="decimal"
          aria-label="Ir para o capítulo"
          placeholder="Ir para o capítulo…"
          maxLength={10}
          autoComplete="off"
          data-testid="goto-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <button type="submit" className="btn" data-testid="goto-submit">
          Ir
        </button>
      </form>
      {problem && (
        <p className="alert alert--error" role="alert" data-testid="goto-error">
          {problem}
        </p>
      )}
      <ul className="chapter-list" data-testid="chapter-list">
        {list.visible.map((chapter) => (
          <ChapterRow
            key={chapter.id}
            chapter={chapter}
            seriesId={seriesId}
            highlighted={chapter.id === list.highlightId}
          />
        ))}
      </ul>
      {list.remaining > 0 && (
        <button
          type="button"
          className="btn series__more"
          data-testid="chapters-more"
          onClick={list.showMore}
        >
          Mostrar mais capítulos ({list.remaining} restantes)
        </button>
      )}
    </section>
  );
}
