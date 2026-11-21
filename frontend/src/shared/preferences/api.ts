import { apiClient } from '../api-client';
import { normalizePreferences, type Preferences } from './types';

export async function fetchPreferences(signal?: AbortSignal): Promise<Preferences> {
  return normalizePreferences(await apiClient.get<unknown>('/api/v1/me/preferences', signal));
}

export async function savePreferences(preferences: Preferences): Promise<Preferences> {
  return normalizePreferences(await apiClient.put<unknown>('/api/v1/me/preferences', preferences));
}
