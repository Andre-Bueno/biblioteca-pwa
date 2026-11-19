import { describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  NetworkError,
  RateLimitError,
  createApiClient,
} from '../../src/shared/api-client';
import { credentialsFor } from '../../src/shared/api-client/client';
import { readCookie } from '../../src/shared/api-client/csrf';

function setup(response: Response | Error, cookies: Record<string, string> = {}) {
  const fetchImpl = vi.fn<typeof fetch>(async () => {
    if (response instanceof Error) throw response;
    return response;
  });
  const client = createApiClient({
    baseUrl: 'http://api.test',
    csrfCookieName: 'csrf_token',
    csrfHeaderName: 'X-CSRF-Token',
    fetchImpl,
    getCookie: (name) => cookies[name] ?? null,
  });
  return { client, fetchImpl };
}

const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(body), { status, headers });

describe('api-client', () => {
  it('sends credentials and no CSRF header on GET', async () => {
    const { client, fetchImpl } = setup(json({ ok: true }), { csrf_token: 'abc' });
    await expect(client.get('/api/v1/health')).resolves.toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('http://api.test/api/v1/health');
    expect(init?.credentials).toBe('include');
    expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined();
  });

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'])('sends the CSRF header on %s', async (method) => {
    const { client, fetchImpl } = setup(json({}), { csrf_token: 'abc' });
    await client.request('/x', { method, body: { a: 1 } });
    const init = fetchImpl.mock.calls[0]![1]!;
    expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBe('abc');
    expect(init.credentials).toBe('include');
    expect(init.body).toBe('{"a":1}');
  });

  it('omits the CSRF header when the cookie is missing', async () => {
    const { client, fetchImpl } = setup(json({}));
    await client.post('/x', {});
    expect(
      (fetchImpl.mock.calls[0]![1]!.headers as Record<string, string>)['X-CSRF-Token'],
    ).toBeUndefined();
  });

  it('maps 429 to a generic RateLimitError', async () => {
    const { client } = setup(json({ detail: 'user alice exists' }, 429, { 'Retry-After': '30' }));
    const error = await client.post('/api/v1/auth/login', {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RateLimitError);
    expect((error as RateLimitError).retryAfterSeconds).toBe(30);
    expect((error as RateLimitError).message).not.toMatch(/alice|exists|usu/i);
  });

  it('maps other failures to ApiError without leaking the body', async () => {
    const { client } = setup(json({ detail: 'secret' }, 500));
    const error = await client.get('/x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(500);
    expect((error as ApiError).message).not.toContain('secret');
  });

  it('maps network failures to NetworkError', async () => {
    const { client } = setup(new TypeError('failed'));
    await expect(client.get('/x')).rejects.toBeInstanceOf(NetworkError);
  });

  it('returns undefined on 204', async () => {
    const { client } = setup(new Response(null, { status: 204 }));
    await expect(client.delete('/x')).resolves.toBeUndefined();
  });
});

describe('api-client robustness', () => {
  it('turns a non-JSON 200 body into a generic ApiError (not SyntaxError)', async () => {
    const { client } = setup(new Response('<html>portal</html>', { status: 200 }));
    const error = await client.get('/x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(SyntaxError);
    expect((error as ApiError).status).toBe(200);
    expect((error as ApiError).message).not.toContain('portal');
  });

  it('propagates AbortError untouched', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    const { client } = setup(abort);
    await expect(client.get('/x')).rejects.toBe(abort);
  });

  it('propagates AbortError raised while reading the body', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    const fake = {
      ok: true,
      status: 200,
      headers: new Headers(),
      text: async () => {
        throw abort;
      },
    } as unknown as Response;
    const { client } = setup(fake);
    await expect(client.get('/x')).rejects.toBe(abort);
  });

  it('maps a non-abort body read failure to NetworkError', async () => {
    const fake = {
      ok: true,
      status: 200,
      headers: new Headers(),
      text: async () => {
        throw new TypeError('stream broke');
      },
    } as unknown as Response;
    const { client } = setup(fake);
    await expect(client.get('/x')).rejects.toBeInstanceOf(NetworkError);
  });

  it.each(['', '   \n'])('resolves undefined on a 200 with empty body %j', async (body) => {
    const { client } = setup(new Response(body, { status: 200 }));
    await expect(client.post('/x', {})).resolves.toBeUndefined();
  });

  it.each([
    ['http://api.test/', '/x', 'http://api.test/x'],
    ['http://api.test///', '/x', 'http://api.test/x'],
    ['http://api.test', '/x', 'http://api.test/x'],
    ['', '/x', '/x'],
    ['/api/', '/x', '/api/x'],
    ['http://api.test/', 'x', 'http://api.test/x'],
  ])('joins baseUrl %j and path %j as %j', async (baseUrl, path, expected) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => json({}));
    const client = createApiClient({
      baseUrl,
      csrfCookieName: 'c',
      csrfHeaderName: 'h',
      fetchImpl,
    });
    await client.get(path);
    expect(fetchImpl.mock.calls[0]![0]).toBe(expected);
  });

  it('maps 429 without Retry-After to retryAfterSeconds null', async () => {
    const { client } = setup(json({}, 429));
    const error = await client.get('/x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RateLimitError);
    expect((error as RateLimitError).retryAfterSeconds).toBeNull();
  });
});

describe('credentials mode', () => {
  it.each([
    ['', 'same-origin'],
    ['/api', 'same-origin'],
    ['http://app.test', 'same-origin'],
    ['http://api.test', 'include'],
    ['//api.test', 'include'],
  ])('baseUrl %j uses %s', (baseUrl, expected) => {
    expect(credentialsFor(baseUrl, 'http://app.test')).toBe(expected);
  });

  it('uses same-origin on requests when baseUrl is empty', async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => json({}));
    const client = createApiClient({
      baseUrl: '',
      csrfCookieName: 'c',
      csrfHeaderName: 'h',
      fetchImpl,
    });
    await client.get('/x');
    expect(fetchImpl.mock.calls[0]![1]!.credentials).toBe('same-origin');
  });
});

describe('readCookie', () => {
  it('reads and decodes a cookie', () => {
    expect(readCookie('b', 'a=1; b=x%20y; c=3')).toBe('x y');
    expect(readCookie('z', 'a=1')).toBeNull();
  });
});
