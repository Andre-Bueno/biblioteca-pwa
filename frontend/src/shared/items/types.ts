export type ItemType = 'manga' | 'book' | 'pdf';

export interface Item {
  id: string;
  type: ItemType;
  title: string;
  format: string;
  page_count: number | null;
  added_at: string;
  has_cover: boolean;
  /** Present once the backend groups chapters into series. */
  series_id?: string | null;
}

export interface ItemList {
  items: Item[];
  limit: number;
  offset: number;
  has_more: boolean;
}

/** Manga (CBZ/folder) and books (EPUB) can be opened; PDFs show "em breve". */
export function isReadable(item: Pick<Item, 'type'>): boolean {
  return item.type === 'manga' || item.type === 'book';
}

export interface BookChapter {
  index: number;
  title: string;
}

export interface BookTocEntry {
  title: string;
  index: number;
  anchor: string | null;
}

/** Structure of an EPUB. Every string is plain text (React escapes it). */
export interface BookInfo {
  title: string;
  authors: string[];
  language: string | null;
  chapters: BookChapter[];
  toc: BookTocEntry[];
  has_cover: boolean;
}
