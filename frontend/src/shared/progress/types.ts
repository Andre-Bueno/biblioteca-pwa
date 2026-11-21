import type { Item } from '../items';

export interface Progress {
  item_id: string;
  locator: number;
  /** 0 to 100. */
  percent: number;
  finished: boolean;
  updated_at: string;
}

export interface ContinueEntry {
  item: Item;
  series_id?: string | null;
  series_title?: string | null;
  locator: number;
  percent: number;
  finished: boolean;
  updated_at: string;
}

export interface ContinueList {
  items: ContinueEntry[];
}

export type SaveStatus = 'idle' | 'saving' | 'error';
