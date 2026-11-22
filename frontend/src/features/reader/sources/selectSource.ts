import type { ItemType } from '../../../shared/items';
import { createBookChaptersSource, type BookSourceInfo } from './chaptersSource';
import { createImagePagesSource } from './pagesSource';
import type { ReaderSource } from './types';

export interface SourceData {
  /** Page count of an image item (manga, PDF). */
  pageCount: number;
  /** Structure of a book; missing means no chapters yet. */
  book?: BookSourceInfo | null;
}

/** book -> chapters; manga and pdf -> pages. The locator codec depends on the item type. */
export function selectSource(type: ItemType, data: SourceData): ReaderSource {
  if (type === 'book') return createBookChaptersSource(data.book ?? { chapters: [], toc: [] });
  return createImagePagesSource(data.pageCount);
}
