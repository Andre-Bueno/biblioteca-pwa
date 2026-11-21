import { apiClient } from '../api-client';
import type { SessionUser } from './types';

export function fetchMe(signal?: AbortSignal): Promise<SessionUser> {
  return apiClient.get<SessionUser>('/api/v1/auth/me', signal);
}

export function postLogin(username: string, password: string): Promise<SessionUser> {
  return apiClient.post<SessionUser>('/api/v1/auth/login', { username, password });
}

export function postLogout(): Promise<void> {
  return apiClient.post<void>('/api/v1/auth/logout');
}

export function postChangePassword(currentPassword: string, newPassword: string): Promise<void> {
  return apiClient.post<void>('/api/v1/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
}
