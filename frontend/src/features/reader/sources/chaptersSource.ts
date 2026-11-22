import type { BookChapter, BookTocEntry } from '../../../shared/items';
import { bookPercent, clampChapter, decodeLocator, encodeLocator } from '../epub/locator';
import type { LocatorCodec, ReaderSource, TocItem } from './types';

/** Locator of a book is `chapter * 10000 + offset_bp` (same rule as the server). */
export const chaptersCodec: LocatorCodec = {
  decode(locator) {
    const { chapter, bp } = decodeLocator(locator);
    return { unit: chapter, bp };
  },
  encode: encodeLocator,
  percent: bookPercent,
};

export interface BookSourceInfo {
  chapters: readonly BookChapter[];
  toc: readonly BookTocEntry[];
}

/** EPUB: one HTML chapter per unit, shown in a sandboxed frame. */
export function createBookChaptersSource(book: BookSourceInfo): ReaderSource {
  const unitCount = book.chapters.length;
  const toc: TocItem[] = book.toc.map((entry) => ({
    title: entry.title,
    unit: entry.index,
    anchor: entry.anchor,
  }));
  return {
    kind: 'chapters',
    unitCount,
    codec: chaptersCodec,
    toc,
    capabilities: {
      textSettings: true,
      zoomToggle: false,
      edgeTapsStep: false,
      // Keys, swipe and the slider follow rtl/ltr for text too (the sides do not turn chapters).
      honorsDirection: true,
    },
    clampUnit: (unit) => clampChapter(unit, unitCount),
    unitTitle: (unit) => {
      const index = clampChapter(unit, unitCount);
      const title = book.chapters.at(index)?.title ?? '';
      return title || `Capítulo ${index + 1}`;
    },
  };
}
