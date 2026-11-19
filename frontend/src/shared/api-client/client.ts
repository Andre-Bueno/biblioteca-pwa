import { isStateChanging, readCookie } from './csrf';
import { ApiError, NetworkError, RateLimitError } from './errors';

export interface ApiClientConfig {
  baseUrl: string;
  csrfCookieName: string;
  csrfHeaderName: string;
  fetchImpl?: typeof globalThis.fetch;
  /** Overridable for tests; defaults to reading document.cookie. */
  getCookie?: (name: string) => string | null;
  /** Overridable for tests; defaults to window.location.origin. */
  currentOrigin?: string;
}

/**
 * Cookies (session + CSRF) are sent with same-origin when the API lives on the same origin
 * (empty or relative baseUrl, or an absolute URL equal to the page origin). include is used only
 * when a different origin is explicitly configured, which also requires CORS with credentials.
 */
export function credentialsFor(baseUrl: string, currentOrigin?: string): RequestCredentials {
  const here = currentOrigin ?? globalThis.location?.origin;
  if (baseUrl === '' || !here) return 'same-origin';
  try {
    // Resolving against the page origin handles relative and protocol-relative (//host) values.
    return new URL(baseUrl, here).origin === here ? 'same-origin' : 'include';
  } catch {
    return 'same-origin';
  }
}

// DOMException may not be an Error across realms, so check the name only.
function isAbortError(error: unknown): boolean {
  return (error as { name?: unknown } | null)?.name === 'AbortError';
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

export interface ApiClient {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  get<T>(path: string, signal?: AbortSignal): Promise<T>;
  post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>;
  put<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>;
  delete<T>(path: string, signal?: AbortSignal): Promise<T>;
}

export function createApiClient(config: ApiClientConfig): ApiClient {
  const doFetch = config.fetchImpl ?? ((...args) => globalThis.fetch(...args));
  const getCookie = config.getCookie ?? ((name: string) => readCookie(name));
  const baseUrl = config.baseUrl.replace(/\/+$/, ''); // no double slash when joining with "/path"
  const credentials = credentialsFor(baseUrl, config.currentOrigin);

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = (options.method ?? 'GET').toUpperCase();
    const headers: Record<string, string> = { Accept: 'application/json' };
    const init: RequestInit = { method, headers, credentials, signal: options.signal };

    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(options.body);
    }
    if (isStateChanging(method)) {
      const token = getCookie(config.csrfCookieName);
      if (token) headers[config.csrfHeaderName] = token;
    }

    let response: Response;
    try {
      response = await doFetch(`${baseUrl}${path.startsWith('/') ? path : `/${path}`}`, init);
    } catch (error) {
      if (isAbortError(error)) throw error;
      throw new NetworkError();
    }

    if (response.status === 429) {
      const retry = Number(response.headers.get('Retry-After'));
      throw new RateLimitError(Number.isFinite(retry) && retry > 0 ? retry : null);
    }
    if (!response.ok) {
      throw new ApiError(response.status, `Falha na requisição (${response.status}).`);
    }
    // Empty success (204, or 2xx with an empty body) is explicit: resolves to undefined.
    // Callers that expect a body type T must be prepared for this (the API only returns empty
    // bodies on 204-style endpoints such as logout/delete).
    if (response.status === 204) return undefined as T;
    let text: string;
    try {
      text = await response.text();
    } catch (error) {
      if (isAbortError(error)) throw error; // aborted while reading the body
      throw new NetworkError();
    }
    if (text.trim() === '') return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      // e.g. 200 with an HTML body (captive portal, proxy error page): never surface a SyntaxError.
      throw new ApiError(response.status, 'Resposta inesperada do servidor.');
    }
  }

  return {
    request,
    get: (path, signal) => request(path, { signal }),
    post: (path, body, signal) => request(path, { method: 'POST', body, signal }),
    put: (path, body, signal) => request(path, { method: 'PUT', body, signal }),
    delete: (path, signal) => request(path, { method: 'DELETE', signal }),
  };
}

export const apiClient: ApiClient = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  csrfCookieName: import.meta.env.VITE_CSRF_COOKIE_NAME ?? 'csrf_token',
  csrfHeaderName: import.meta.env.VITE_CSRF_HEADER_NAME ?? 'X-CSRF-Token',
});
