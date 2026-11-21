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

/** Only manga (CBZ/folder) can be opened today; books and PDFs show "em breve". */
export function isReadable(item: Pick<Item, 'type'>): boolean {
  return item.type === 'manga';
}
