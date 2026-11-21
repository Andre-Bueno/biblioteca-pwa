import { apiClient } from '../api-client';
import type { EnrichStatus, MetadataCandidate, SeriesDetail, SeriesList } from './types';

export interface ListSeriesParams {
  q?: string;
  limit?: number;
  offset?: number;
}

export function listSeries(params: ListSeriesParams, signal?: AbortSignal): Promise<SeriesList> {
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset) query.set('offset', String(params.offset));
  const text = query.toString();
  return apiClient.get<SeriesList>(`/api/v1/series${text ? `?${text}` : ''}`, signal);
}

export function getSeries(id: string, signal?: AbortSignal): Promise<SeriesDetail> {
  return apiClient.get<SeriesDetail>(`/api/v1/series/${encodeURIComponent(id)}`, signal);
}

/**
 * Same-origin image URL: the session cookie travels with <img>. `version` (a local counter, > 0)
 * is only a cache-busting querystring after the metadata changed; never an external URL.
 */
export function seriesCoverUrl(id: string, version = 0): string {
  const base = `/api/v1/series/${encodeURIComponent(id)}/cover`;
  return version > 0 ? `${base}?v=${version}` : base;
}

const metadataPath = (id: string) => `/api/v1/series/${encodeURIComponent(id)}/metadata`;

export function startEnrich(): Promise<void> {
  return apiClient.post<void>('/api/v1/library/enrich');
}

export function getEnrichStatus(signal?: AbortSignal): Promise<EnrichStatus> {
  return apiClient.get<EnrichStatus>('/api/v1/library/enrich/status', signal);
}

export async function searchMetadataCandidates(
  id: string,
  q: string,
  signal?: AbortSignal,
): Promise<MetadataCandidate[]> {
  const data = await apiClient.get<{ items: MetadataCandidate[] }>(
    `${metadataPath(id)}/candidates?${new URLSearchParams({ q }).toString()}`,
    signal,
  );
  return data?.items ?? [];
}

export function selectMetadata(
  id: string,
  choice: { provider: string; external_id: string },
): Promise<unknown> {
  return apiClient.post<unknown>(`${metadataPath(id)}/select`, choice);
}

export function saveMetadataText(
  id: string,
  body: { title?: string; description?: string },
): Promise<unknown> {
  return apiClient.put<unknown>(metadataPath(id), body);
}

export function removeMetadata(id: string): Promise<void> {
  return apiClient.delete<void>(metadataPath(id));
}
