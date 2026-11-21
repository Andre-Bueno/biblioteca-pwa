import { ApiError, apiClient } from '../api-client';
import type { ContinueEntry, ContinueList, Progress } from './types';

const base = (itemId: string) => `/api/v1/progress/${encodeURIComponent(itemId)}`;

/** Resolves null when the item has no progress yet (404). */
export async function getProgress(itemId: string, signal?: AbortSignal): Promise<Progress | null> {
  try {
    return await apiClient.get<Progress>(base(itemId), signal);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function putProgress(
  itemId: string,
  locator: number,
  options: { keepalive?: boolean; signal?: AbortSignal } = {},
): Promise<Progress> {
  return apiClient.request<Progress>(base(itemId), {
    method: 'PUT',
    body: { locator },
    keepalive: options.keepalive,
    signal: options.signal,
  });
}

export function deleteProgress(itemId: string): Promise<void> {
  return apiClient.delete<void>(base(itemId));
}

export async function listContinue(limit = 12, signal?: AbortSignal): Promise<ContinueEntry[]> {
  const data = await apiClient.get<ContinueList>(
    `/api/v1/progress/continue?limit=${Math.trunc(limit)}`,
    signal,
  );
  return data?.items ?? [];
}
