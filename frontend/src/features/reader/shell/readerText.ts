import type { SourceKind } from '../sources';

/**
 * Words and test ids that depend on what a unit is. The shell is the same for every format; only
 * this table changes between "page" (image items) and "chapter" (books).
 */
export interface ReaderText {
  /** Capitalised name of a unit, for "Capítulo 3 de 10". */
  unitName: string;
  sliderLabel: string;
  prevLabel: string;
  nextLabel: string;
  /** Long status in the bottom bar. */
  status: (unit: number, count: number, percent: number) => string;
  /** Short hint shown while the bars are hidden. */
  pill: (unit: number, count: number, percent: number) => string;
  /** The hint is read aloud on change (useful per page, noisy while a chapter scrolls). */
  announcePill: boolean;
  testIds: {
    title: string;
    slider: string;
    prev: string;
    next: string;
    status: string;
    pill: string;
  };
  end: {
    /** Name of the region when the last unit is reached. */
    lastRegion: string;
    /** Shown only once the series order is known (a lone page item has nothing to offer). */
    needsSeries: boolean;
    finished: { text: string; testId: string; alwaysShown: boolean };
    next: { label: string; testId: string };
    previous: { label: string; testId: string };
  };
}

export const READER_TEXT: Record<SourceKind, ReaderText> = {
  pages: {
    unitName: 'Página',
    sliderLabel: 'Ir para a página',
    prevLabel: 'Voltar página',
    nextLabel: 'Avançar página',
    status: (unit, count) => `${unit + 1} / ${count}`,
    pill: (unit, count) => `${unit + 1} / ${count}`,
    announcePill: true,
    testIds: {
      title: 'reader-title',
      slider: 'page-slider',
      prev: 'page-prev',
      next: 'page-next',
      status: 'page-indicator',
      pill: 'page-indicator',
    },
    end: {
      lastRegion: 'Fim do capítulo',
      needsSeries: true,
      finished: {
        text: 'Você chegou ao último capítulo.',
        testId: 'series-finished',
        alwaysShown: false,
      },
      next: { label: 'Próximo capítulo ›', testId: 'next-chapter' },
      previous: { label: '‹ Capítulo anterior', testId: 'previous-chapter' },
    },
  },
  chapters: {
    unitName: 'Capítulo',
    sliderLabel: 'Ir para o capítulo',
    prevLabel: 'Capítulo anterior',
    nextLabel: 'Próximo capítulo',
    status: (unit, count, percent) => `Capítulo ${unit + 1} de ${count} · ${percent}%`,
    pill: (unit, count, percent) => `${unit + 1}/${count} · ${percent}%`,
    announcePill: false,
    testIds: {
      title: 'book-title',
      slider: 'chapter-slider',
      prev: 'chapter-prev',
      next: 'chapter-next',
      status: 'chapter-indicator',
      pill: 'epub-pill',
    },
    end: {
      lastRegion: 'Fim do livro',
      needsSeries: false,
      finished: {
        text: 'Você chegou ao fim do livro.',
        testId: 'book-finished',
        alwaysShown: true,
      },
      next: { label: 'Próximo livro ›', testId: 'next-book' },
      previous: { label: '‹ Livro anterior', testId: 'previous-book' },
    },
  },
};
