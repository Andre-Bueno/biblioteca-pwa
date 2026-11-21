export type UpdateState = 'idle' | 'requested' | 'failed';

export interface LatestRelease {
  tag: string;
  version: string;
  name: string;
  /** Plain text (never HTML), at most 4000 characters. */
  notes: string;
  published_at: string | null;
  /** Only an https URL survives; anything else is null. */
  url: string | null;
}

/**
 * `GET /system/version` and `POST /system/update/check`. Regular users only get `current` and
 * `update_available`; the other fields exist for admins (and are defaulted here otherwise).
 */
export interface VersionInfo {
  current: string;
  update_available: boolean;
  latest: LatestRelease | null;
  checked_at: string | null;
  webhook_configured: boolean;
  update: { state: UpdateState; tag: string | null; requested_at: string | null };
}

export interface UpdateRequested {
  state: 'requested';
  tag: string;
  requested_at: string | null;
}

export const NOTES_MAX = 4000;

/** "v1.3.0" and "1.3.0" are the same version. */
export function versionOfTag(tag: string): string {
  return tag.replace(/^v/i, '');
}
