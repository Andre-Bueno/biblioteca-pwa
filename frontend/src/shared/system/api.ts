import { apiClient } from '../api-client';
import { safeHttpsUrl } from '../series';
import {
  NOTES_MAX,
  type LatestRelease,
  type UpdateRequested,
  type UpdateState,
  type VersionInfo,
} from './types';

const text = (value: unknown): string => (typeof value === 'string' ? value : '');
const orNull = (value: unknown): string | null =>
  typeof value === 'string' && value !== '' ? value : null;

function normalizeLatest(raw: unknown): LatestRelease | null {
  const data = (raw ?? {}) as Record<string, unknown>;
  const tag = orNull(data.tag);
  if (!tag) return null;
  return {
    tag,
    version: text(data.version) || tag.replace(/^v/i, ''),
    name: text(data.name),
    notes: text(data.notes).slice(0, NOTES_MAX),
    published_at: orNull(data.published_at),
    url: safeHttpsUrl(orNull(data.url)),
  };
}

/** The server is not trusted to be well-formed: keep only what has the expected shape. */
export function normalizeVersion(raw: unknown): VersionInfo {
  const data = (raw ?? {}) as Record<string, unknown>;
  const update = (data.update ?? {}) as Record<string, unknown>;
  const state: UpdateState =
    update.state === 'requested' || update.state === 'failed' ? update.state : 'idle';
  return {
    current: text(data.current),
    update_available: data.update_available === true,
    latest: normalizeLatest(data.latest),
    checked_at: orNull(data.checked_at),
    webhook_configured: data.webhook_configured === true,
    update: { state, tag: orNull(update.tag), requested_at: orNull(update.requested_at) },
  };
}

export async function getVersion(signal?: AbortSignal): Promise<VersionInfo> {
  return normalizeVersion(await apiClient.get<unknown>('/api/v1/system/version', signal));
}

/** Admin only; the server limits this to 3 per minute (429). */
export async function checkForUpdates(signal?: AbortSignal): Promise<VersionInfo> {
  return normalizeVersion(
    await apiClient.post<unknown>('/api/v1/system/update/check', undefined, signal),
  );
}

/** Admin only. The server calls its deploy webhook; the app never sees the webhook. */
export async function requestUpdate(tag: string, signal?: AbortSignal): Promise<UpdateRequested> {
  const data = await apiClient.post<Record<string, unknown> | undefined>(
    '/api/v1/system/update',
    { tag },
    signal,
  );
  return {
    state: 'requested',
    tag: orNull(data?.tag) ?? tag,
    requested_at: orNull(data?.requested_at),
  };
}
