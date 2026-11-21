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
  /** Endpoint that issues the csrf_token cookie (GET, 204). */
  csrfPath?: string;
  /** Endpoint that rotates the session cookies (POST, 204). */
  refreshPath?: string;
  /** Paths whose 401 is an answer, not an expired session (login, refresh, csrf, logout). */
  noRefreshPaths?: string[];
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

function retryAfter(response: Response): number | null {
  const value = Number(response.headers.get('Retry-After'));
  return Number.isFinite(value) && value > 0 ? value : null;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Lets the request outlive the page (used to flush reading progress on pagehide). */
  keepalive?: boolean;
}

export interface ApiClient {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  get<T>(path: string, signal?: AbortSignal): Promise<T>;
  post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>;
  put<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>;
  delete<T>(path: string, signal?: AbortSignal): Promise<T>;
  /**
   * Rotates the session cookies. Concurrent callers (and concurrent 401 recoveries) share ONE
   * network call. Resolves false when the session is over (the listeners are notified).
   */
  refreshSession(): Promise<boolean>;
  /** Called when the session could not be recovered (refresh rejected). Returns unsubscribe. */
  onSessionExpired(listener: () => void): () => void;
}

const DEFAULT_NO_REFRESH = [
  '/api/v1/auth/login',
  '/api/v1/auth/refresh',
  '/api/v1/auth/csrf',
  '/api/v1/auth/logout',
];

export function createApiClient(config: ApiClientConfig): ApiClient {
  const doFetch = config.fetchImpl ?? ((...args) => globalThis.fetch(...args));
  const getCookie = config.getCookie ?? ((name: string) => readCookie(name));
  const baseUrl = config.baseUrl.replace(/\/+$/, ''); // no double slash when joining with "/path"
  const credentials = credentialsFor(baseUrl, config.currentOrigin);
  const csrfPath = config.csrfPath ?? '/api/v1/auth/csrf';
  const refreshPath = config.refreshPath ?? '/api/v1/auth/refresh';
  const noRefresh = new Set(config.noRefreshPaths ?? DEFAULT_NO_REFRESH);

  const expiredListeners = new Set<() => void>();
  let csrfInflight: Promise<void> | null = null;
  let refreshInflight: Promise<boolean> | null = null;
  // Bumped after each successful refresh: a request that started before it and got a (late) 401
  // just retries instead of triggering another rotation.
  let refreshGeneration = 0;

  const notifyExpired = () => expiredListeners.forEach((listener) => listener());

  async function send(path: string, options: RequestOptions): Promise<Response> {
    const method = (options.method ?? 'GET').toUpperCase();
    const headers: Record<string, string> = { Accept: 'application/json' };
    const init: RequestInit = { method, headers, credentials, signal: options.signal };
    if (options.keepalive) init.keepalive = true;

    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(options.body);
    }
    if (isStateChanging(method)) {
      const token = getCookie(config.csrfCookieName);
      if (token) headers[config.csrfHeaderName] = token;
    }
    try {
      return await doFetch(`${baseUrl}${path.startsWith('/') ? path : `/${path}`}`, init);
    } catch (error) {
      if (isAbortError(error)) throw error;
      throw new NetworkError();
    }
  }

  /** One shared GET to the csrf endpoint; the server sets the cookie. */
  function fetchCsrf(): Promise<void> {
    csrfInflight ??= (async () => {
      try {
        const response = await send(csrfPath, {});
        if (response.status === 429) throw new RateLimitError(retryAfter(response));
        if (!response.ok) throw new ApiError(response.status, 'Falha ao preparar a requisição.');
      } finally {
        csrfInflight = null;
      }
    })();
    return csrfInflight;
  }

  async function ensureCsrf(): Promise<void> {
    if (!getCookie(config.csrfCookieName)) await fetchCsrf();
  }

  async function runRefresh(): Promise<boolean> {
    // The csrf cookie lives as long as the refresh token and is readable by JS (same origin).
    // Without it there cannot be a session to refresh: skip the useless csrf + refresh calls
    // (cold start of a signed-out visitor).
    if (credentials === 'same-origin' && !getCookie(config.csrfCookieName)) return false;
    await ensureCsrf();
    const response = await send(refreshPath, { method: 'POST' });
    if (response.ok) {
      refreshGeneration += 1;
      return true;
    }
    if (response.status === 401 || response.status === 403) return false; // session is over
    if (response.status === 429) throw new RateLimitError(retryAfter(response));
    throw new ApiError(response.status, `Falha na requisição (${response.status}).`);
  }

  function refreshShared(startedAtGeneration: number): Promise<boolean> {
    if (refreshGeneration !== startedAtGeneration) return Promise.resolve(true);
    refreshInflight ??= (async () => {
      try {
        // Web Locks serialize the rotation across tabs (cookies are shared by all of them).
        const locks = globalThis.navigator?.locks;
        return locks
          ? await locks.request('biblioteca-session-refresh', runRefresh)
          : await runRefresh();
      } finally {
        refreshInflight = null;
      }
    })();
    return refreshInflight;
  }

  async function refreshSession(): Promise<boolean> {
    const ok = await refreshShared(refreshGeneration);
    if (!ok) notifyExpired();
    return ok;
  }

  async function parse<T>(response: Response): Promise<T> {
    if (response.status === 429) throw new RateLimitError(retryAfter(response));
    if (!response.ok) {
      throw new ApiError(
        response.status,
        `Falha na requisição (${response.status}).`,
        retryAfter(response),
      );
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

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = (options.method ?? 'GET').toUpperCase();
    const mutating = isStateChanging(method);
    if (mutating && path !== csrfPath) await ensureCsrf();

    const startedAtGeneration = refreshGeneration;
    let response = await send(path, options);

    // 403 on a mutation: the CSRF token may be stale. Refetch and retry ONCE, but only when the
    // server actually handed us a different token (a plain "Forbidden" is not retried).
    if (response.status === 403 && mutating && path !== csrfPath) {
      const before = getCookie(config.csrfCookieName);
      await fetchCsrf();
      const after = getCookie(config.csrfCookieName);
      if (after && after !== before) response = await send(path, options);
    }

    // 401 on an authenticated call: rotate the session (one shared refresh) and retry ONCE.
    if (response.status === 401 && !noRefresh.has(path)) {
      const refreshed = await refreshShared(startedAtGeneration);
      if (refreshed) {
        response = await send(path, options);
        if (response.status === 401) notifyExpired();
      } else {
        notifyExpired();
      }
    }

    return parse<T>(response);
  }

  return {
    request,
    get: (path, signal) => request(path, { signal }),
    post: (path, body, signal) => request(path, { method: 'POST', body, signal }),
    put: (path, body, signal) => request(path, { method: 'PUT', body, signal }),
    delete: (path, signal) => request(path, { method: 'DELETE', signal }),
    refreshSession,
    onSessionExpired(listener) {
      expiredListeners.add(listener);
      return () => expiredListeners.delete(listener);
    },
  };
}

export const apiClient: ApiClient = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  csrfCookieName: import.meta.env.VITE_CSRF_COOKIE_NAME ?? 'csrf_token',
  csrfHeaderName: import.meta.env.VITE_CSRF_HEADER_NAME ?? 'X-CSRF-Token',
});
