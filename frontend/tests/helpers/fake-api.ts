import { vi } from 'vitest';
import { ApiError, RateLimitError } from '../../src/shared/api-client/errors';

type Matcher = string | RegExp;
type Handler = (ctx: { body: unknown; path: string }) => unknown;

export interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
  keepalive: boolean;
}

/**
 * In-memory stand-in for the api-client singleton: routes by method + path (query ignored for
 * string matchers), records every call, and lets tests throw ApiError / RateLimitError.
 */
export function createFakeApi() {
  let routes: { method: string; matcher: Matcher; handler: Handler }[] = [];
  const calls: RecordedCall[] = [];

  async function request(
    path: string,
    options: { method?: string; body?: unknown; keepalive?: boolean; signal?: AbortSignal } = {},
  ) {
    const method = (options.method ?? 'GET').toUpperCase();
    calls.push({ method, path, body: options.body, keepalive: options.keepalive === true });
    const bare = path.split('?')[0]!;
    // Latest registration wins, so tests can override the defaults.
    const route = [...routes]
      .reverse()
      .find(
        (r) =>
          r.method === method &&
          (typeof r.matcher === 'string' ? r.matcher === bare : r.matcher.test(path)),
      );
    if (!route) throw new ApiError(404, 'not found');
    return route.handler({ body: options.body, path });
  }

  const api = {
    request,
    get: (path: string, signal?: AbortSignal) => request(path, { signal }),
    post: (path: string, body?: unknown) => request(path, { method: 'POST', body }),
    put: (path: string, body?: unknown) => request(path, { method: 'PUT', body }),
    delete: (path: string) => request(path, { method: 'DELETE' }),
    refreshSession: vi.fn(async () => true),
    onSessionExpired: vi.fn((listener: () => void) => {
      void listener;
      return () => undefined;
    }),
  };

  return {
    api,
    calls,
    on(method: string, matcher: Matcher, result: Handler | object | null | undefined) {
      const handler: Handler = typeof result === 'function' ? (result as Handler) : () => result;
      routes.push({ method: method.toUpperCase(), matcher, handler });
    },
    reset() {
      routes = [];
      calls.length = 0;
      api.refreshSession.mockClear();
      api.onSessionExpired.mockClear();
    },
    callsTo(method: string, matcher: Matcher) {
      return calls.filter(
        (c) =>
          c.method === method.toUpperCase() &&
          (typeof matcher === 'string' ? c.path.split('?')[0] === matcher : matcher.test(c.path)),
      );
    },
  };
}

export const fakeApi = createFakeApi();

export const apiError = (status: number) => () => {
  throw new ApiError(status, 'x');
};
export const rateLimited = (seconds: number | null) => () => {
  throw new RateLimitError(seconds);
};

export const USER = { id: 'u1', username: 'alice', role: 'user', theme_pref: 'system' };

export function makeItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 'item-1',
    type: 'manga',
    title: 'Manga Um',
    format: 'cbz',
    page_count: 10,
    added_at: '2026-01-01T00:00:00Z',
    has_cover: true,
    ...overrides,
  };
}

export function makeSeries(overrides: Record<string, unknown> = {}) {
  return {
    id: 'serie-1',
    title: 'Serie Um',
    chapter_count: 10,
    has_cover: true,
    description: null,
    description_lang: null,
    metadata_state: 'none',
    progress: { read_chapters: 0, last_item_id: null },
    ...overrides,
  };
}

export function makeChapter(n: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `ch-${n}`,
    title: `Capitulo - ${n}`,
    number: n,
    page_count: 10,
    progress: null,
    ...overrides,
  };
}

export function makeSeriesDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: 'serie-1',
    title: 'Serie Um',
    description: null,
    description_lang: null,
    source: null,
    metadata_state: 'none',
    chapter_count: 3,
    has_cover: true,
    chapters: [makeChapter(1), makeChapter(2), makeChapter(3)],
    continue: null,
    ...overrides,
  };
}

/** Defaults for a signed-in user; tests override what they need. */
export function signedIn() {
  fakeApi.on('GET', '/api/v1/auth/me', USER);
  fakeApi.on('GET', '/api/v1/me/preferences', { theme: 'system', reading_direction: 'rtl' });
  fakeApi.on('PUT', '/api/v1/me/preferences', ({ body }) => body);
  fakeApi.on('GET', '/api/v1/progress/continue', { items: [] });
  fakeApi.on('GET', '/api/v1/items', { items: [], limit: 30, offset: 0, has_more: false });
  fakeApi.on('GET', '/api/v1/series', { items: [], limit: 30, offset: 0, has_more: false });
}
