import { apiClient } from '../api-client';
import type { BookInfo, Item, ItemList, ItemType } from './types';

export interface ListItemsParams {
  type?: ItemType;
  q?: string;
  limit?: number;
  offset?: number;
}

export function listItems(params: ListItemsParams, signal?: AbortSignal): Promise<ItemList> {
  const query = new URLSearchParams();
  if (params.type) query.set('type', params.type);
  if (params.q) query.set('q', params.q);
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset) query.set('offset', String(params.offset));
  const text = query.toString();
  const suffix = text ? `?${text}` : '';
  return apiClient.get<ItemList>(`/api/v1/items${suffix}`, signal);
}

export function getItem(id: string, signal?: AbortSignal): Promise<Item> {
  return apiClient.get<Item>(`/api/v1/items/${encodeURIComponent(id)}`, signal);
}

/** Image URLs are same-origin: the session cookie travels with <img>. */
export function coverUrl(id: string): string {
  return `/api/v1/items/${encodeURIComponent(id)}/cover`;
}

export function pageUrl(id: string, page: number): string {
  return `/api/v1/items/${encodeURIComponent(id)}/pages/${Math.max(0, Math.trunc(page))}`;
}

const BOOK_THEMES = ['auto', 'light', 'dark', 'sepia'];

function asText(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const asIndex = (value: unknown): number | null =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;

/** The server is not trusted to be well-formed: keep only what has the expected shape. */
function normalizeBook(raw: unknown): BookInfo {
  const data = (raw ?? {}) as Record<string, unknown>;
  const chapters: BookInfo['chapters'] = [];
  for (const entry of list(data.chapters)) {
    const row = (entry ?? {}) as Record<string, unknown>;
    const index = asIndex(row.index);
    if (index !== null) chapters.push({ index, title: asText(row.title) });
  }
  const toc: BookInfo['toc'] = [];
  for (const entry of list(data.toc)) {
    const row = (entry ?? {}) as Record<string, unknown>;
    const index = asIndex(row.index);
    if (index === null) continue;
    const anchor = typeof row.anchor === 'string' && row.anchor ? row.anchor : null;
    toc.push({ title: asText(row.title), index, anchor });
  }
  return {
    title: asText(data.title),
    authors: list(data.authors).filter((a): a is string => typeof a === 'string'),
    language: typeof data.language === 'string' ? data.language : null,
    chapters,
    toc,
    has_cover: data.has_cover === true,
  };
}

export async function getBook(id: string, signal?: AbortSignal): Promise<BookInfo> {
  return normalizeBook(
    await apiClient.get<unknown>(`/api/v1/items/${encodeURIComponent(id)}/book`, signal),
  );
}

/**
 * `src` of the chapter iframe. The server sends a complete, sanitized HTML document; theme and
 * font scale are validated here so only known values reach the query string.
 */
export function bookChapterUrl(id: string, chapter: number, theme: string, size: number): string {
  const safeTheme = BOOK_THEMES.includes(theme) ? theme : 'auto';
  const safeSize = Math.min(200, Math.max(80, Math.round(Number.isFinite(size) ? size : 100)));
  const n = Math.max(0, Math.trunc(chapter));
  return `/api/v1/items/${encodeURIComponent(id)}/book/chapters/${n}?theme=${safeTheme}&size=${safeSize}`;
}
