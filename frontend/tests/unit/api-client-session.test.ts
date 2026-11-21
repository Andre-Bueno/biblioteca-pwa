import { describe, expect, it, vi } from 'vitest';
import { ApiError, NetworkError, createApiClient } from '../../src/shared/api-client';

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const empty = (status = 204) => new Response(null, { status });

type Responder = (url: string, init: RequestInit) => Response | Promise<Response>;

function setup(responder: Responder, cookies: Record<string, string> = { csrf_token: 'tok-1' }) {
  const fetchImpl = vi.fn<typeof fetch>(async (input, init) =>
    responder(String(input), init ?? {}),
  );
  const client = createApiClient({
    baseUrl: '',
    csrfCookieName: 'csrf_token',
    csrfHeaderName: 'X-CSRF-Token',
    fetchImpl,
    getCookie: (name) => cookies[name] ?? null,
  });
  const count = (method: string, path: string) =>
    fetchImpl.mock.calls.filter(
      ([url, init]) => String(url) === path && (init?.method ?? 'GET') === method,
    ).length;
  return { client, fetchImpl, cookies, count };
}

describe('api-client session recovery (401 -> refresh -> retry)', () => {
  it('N concurrent 401s trigger exactly ONE refresh and every call is retried once', async () => {
    let refreshed = false;
    let releaseRefresh: () => void = () => undefined;
    const refreshGate = new Promise<void>((resolve) => (releaseRefresh = resolve));
    const { client, count } = setup(async (url) => {
      if (url === '/api/v1/auth/refresh') {
        await refreshGate;
        refreshed = true;
        return empty();
      }
      return refreshed ? json({ ok: true }) : json({ detail: 'Not authenticated' }, 401);
    });

    const calls = Array.from({ length: 6 }, (_, i) => client.get(`/api/v1/items/${i}`));
    // Let every request hit its 401 and queue on the shared refresh before it completes.
    await vi.waitFor(() => expect(count('POST', '/api/v1/auth/refresh')).toBe(1));
    releaseRefresh();
    await expect(Promise.all(calls)).resolves.toHaveLength(6);

    expect(count('POST', '/api/v1/auth/refresh')).toBe(1);
    for (let i = 0; i < 6; i += 1) expect(count('GET', `/api/v1/items/${i}`)).toBe(2);
  });

  it('a late 401 from before the refresh retries without a second rotation', async () => {
    let refreshed = false;
    let releaseSlow: () => void = () => undefined;
    const slowGate = new Promise<void>((resolve) => (releaseSlow = resolve));
    const { client, count } = setup(async (url) => {
      if (url === '/api/v1/auth/refresh') {
        refreshed = true;
        return empty();
      }
      if (url === '/slow' && !refreshed) {
        await slowGate; // the server decided "401" with the old token, but the answer is late
        return json({}, 401);
      }
      return refreshed ? json({ ok: url }) : json({}, 401);
    });

    const slow = client.get('/slow');
    await client.get('/fast'); // 401 -> refresh -> retry succeeds
    expect(count('POST', '/api/v1/auth/refresh')).toBe(1);
    releaseSlow();
    await expect(slow).resolves.toEqual({ ok: '/slow' });
    expect(count('POST', '/api/v1/auth/refresh')).toBe(1);
  });

  it('when refresh is rejected: notifies once, surfaces the 401 and does not loop', async () => {
    const { client, count } = setup((url) =>
      url === '/api/v1/auth/refresh' ? json({}, 401) : json({}, 401),
    );
    const expired = vi.fn();
    client.onSessionExpired(expired);

    const error = await client.get('/api/v1/items').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(count('GET', '/api/v1/items')).toBe(1);
    expect(count('POST', '/api/v1/auth/refresh')).toBe(1);
  });

  it('retries only once: a 401 after a successful refresh is surfaced', async () => {
    const { client, count } = setup((url) =>
      url === '/api/v1/auth/refresh' ? empty() : json({}, 401),
    );
    const expired = vi.fn();
    client.onSessionExpired(expired);
    await expect(client.get('/api/v1/items')).rejects.toMatchObject({ status: 401 });
    expect(count('GET', '/api/v1/items')).toBe(2);
    expect(count('POST', '/api/v1/auth/refresh')).toBe(1);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it.each(['/api/v1/auth/login', '/api/v1/auth/logout'])(
    'a 401 from %s is an answer, not an expired session',
    async (path) => {
      const { client, count } = setup(() => json({ detail: 'Invalid credentials' }, 401));
      await expect(client.post(path, {})).rejects.toMatchObject({ status: 401 });
      expect(count('POST', '/api/v1/auth/refresh')).toBe(0);
    },
  );

  it('does not treat a network failure during refresh as an expired session', async () => {
    const { client } = setup((url) => {
      if (url === '/api/v1/auth/refresh') throw new TypeError('offline');
      return json({}, 401);
    });
    const expired = vi.fn();
    client.onSessionExpired(expired);
    await expect(client.get('/api/v1/items')).rejects.toBeInstanceOf(NetworkError);
    expect(expired).not.toHaveBeenCalled();
  });

  it('signed-out cold start: a 401 with no csrf cookie makes no csrf/refresh calls', async () => {
    const { client, fetchImpl, count } = setup(() => json({}, 401), {});
    const expired = vi.fn();
    client.onSessionExpired(expired);
    await expect(client.get('/api/v1/auth/me')).rejects.toMatchObject({ status: 401 });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(count('GET', '/api/v1/auth/csrf')).toBe(0);
    expect(count('POST', '/api/v1/auth/refresh')).toBe(0);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('refreshSession() shares one call between concurrent callers', async () => {
    const { client, count } = setup(() => empty());
    await Promise.all([client.refreshSession(), client.refreshSession(), client.refreshSession()]);
    expect(count('POST', '/api/v1/auth/refresh')).toBe(1);
  });
});

describe('api-client CSRF bootstrap', () => {
  it('fetches /auth/csrf before the first mutation when the cookie is missing', async () => {
    const cookies: Record<string, string> = {};
    const { client, fetchImpl } = setup((url) => {
      if (url === '/api/v1/auth/csrf') {
        cookies.csrf_token = 'fresh';
        return empty();
      }
      return json({ ok: true });
    }, cookies);

    await client.post('/api/v1/auth/login', { username: 'a', password: 'b' });
    const urls = fetchImpl.mock.calls.map(([url]) => String(url));
    expect(urls).toEqual(['/api/v1/auth/csrf', '/api/v1/auth/login']);
    const headers = fetchImpl.mock.calls[1]![1]!.headers as Record<string, string>;
    expect(headers['X-CSRF-Token']).toBe('fresh');
  });

  it('does not fetch /auth/csrf for GET or when the cookie already exists', async () => {
    const { client, count } = setup(() => json({}));
    await client.get('/x');
    await client.put('/x', {});
    expect(count('GET', '/api/v1/auth/csrf')).toBe(0);
  });

  it('shares ONE csrf fetch between concurrent first mutations', async () => {
    const cookies: Record<string, string> = {};
    const { client, count } = setup(async (url) => {
      if (url === '/api/v1/auth/csrf') {
        await Promise.resolve();
        cookies.csrf_token = 'fresh';
        return empty();
      }
      return json({});
    }, cookies);
    await Promise.all([client.post('/a', {}), client.post('/b', {}), client.put('/c', {})]);
    expect(count('GET', '/api/v1/auth/csrf')).toBe(1);
  });

  it('on 403 refetches the token and retries ONCE when the token changed', async () => {
    const cookies: Record<string, string> = { csrf_token: 'stale' };
    const { client, count } = setup((url, init) => {
      if (url === '/api/v1/auth/csrf') {
        cookies.csrf_token = 'renewed';
        return empty();
      }
      const token = (init.headers as Record<string, string>)['X-CSRF-Token'];
      return token === 'renewed' ? json({ ok: true }) : json({ detail: 'Forbidden' }, 403);
    }, cookies);

    await expect(client.post('/api/v1/progress', {})).resolves.toEqual({ ok: true });
    expect(count('POST', '/api/v1/progress')).toBe(2);
    expect(count('GET', '/api/v1/auth/csrf')).toBe(1);
  });

  it('does not retry a plain 403 when the server hands back the same token', async () => {
    const { client, count } = setup((url) =>
      url === '/api/v1/auth/csrf' ? empty() : json({ detail: 'Forbidden' }, 403),
    );
    await expect(client.post('/x', {})).rejects.toMatchObject({ status: 403 });
    expect(count('POST', '/x')).toBe(1);
  });

  it('retries a 403 only once even if the new token is also rejected', async () => {
    const cookies: Record<string, string> = { csrf_token: 'a' };
    let n = 0;
    const { client, count } = setup((url) => {
      if (url === '/api/v1/auth/csrf') {
        cookies.csrf_token = `t${(n += 1)}`;
        return empty();
      }
      return json({}, 403);
    }, cookies);
    await expect(client.post('/x', {})).rejects.toMatchObject({ status: 403 });
    expect(count('POST', '/x')).toBe(2);
  });
});

describe('api-client keepalive', () => {
  it('passes keepalive to fetch (progress flush on pagehide) and never uses sendBeacon', async () => {
    const beacon = vi.fn();
    vi.stubGlobal('navigator', { ...globalThis.navigator, sendBeacon: beacon });
    const { client, fetchImpl } = setup(() => json({}));
    await client.request('/api/v1/progress/x', {
      method: 'PUT',
      body: { locator: 3 },
      keepalive: true,
    });
    expect(fetchImpl.mock.calls[0]![1]!.keepalive).toBe(true);
    expect(beacon).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
