import { apiClient } from '../api-client';
import type { Item, ItemList, ItemType } from './types';

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
