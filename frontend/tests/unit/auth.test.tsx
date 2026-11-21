import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { safeRedirect } from '../../src/features/auth';
import { USER, apiError, fakeApi, rateLimited, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

async function fillAndSubmit(
  username = 'alice',
  password = 'wrong-password', // secret-scan:allow (fake test value)
) {
  const user = userEvent.setup();
  await user.type(await screen.findByTestId('login-username'), username);
  await user.type(screen.getByTestId('login-password'), password);
  await user.click(screen.getByTestId('login-submit'));
}

describe('route guard', () => {
  beforeEach(() => fakeApi.reset());

  it('shows a loading state while /auth/me is pending, then the protected screen', async () => {
    signedIn();
    let release: (value: unknown) => void = () => undefined;
    fakeApi.on('GET', '/api/v1/auth/me', () => new Promise((resolve) => (release = resolve)));
    renderApp('/');
    expect(screen.getByTestId('session-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('library-page')).not.toBeInTheDocument();
    await act(async () => release(USER));
    expect(await screen.findByTestId('library-page')).toBeInTheDocument();
  });

  it('sends anonymous users to /login from any protected route', async () => {
    signedIn();
    fakeApi.on('GET', '/api/v1/auth/me', apiError(401));
    renderApp('/ler/abc');
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('reader')).not.toBeInTheDocument();
  });

  it('a session that ends elsewhere (refresh rejected) returns to the login', async () => {
    signedIn();
    let expire: () => void = () => undefined;
    fakeApi.api.onSessionExpired.mockImplementation((listener: () => void) => {
      expire = listener;
      return () => undefined;
    });
    renderApp('/');
    expect(await screen.findByTestId('library-page')).toBeInTheDocument();
    act(() => expire());
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
  });

  it('an authenticated user opening /login is sent to the library', async () => {
    signedIn();
    renderApp('/login');
    expect(await screen.findByTestId('library-page')).toBeInTheDocument();
  });
});

describe('login', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
    fakeApi.on('GET', '/api/v1/auth/me', apiError(401));
  });
  afterEach(() => vi.useRealTimers());

  it('signs in and lands on the library', async () => {
    fakeApi.on('POST', '/api/v1/auth/login', USER);
    renderApp('/');
    await fillAndSubmit('alice', 'correct-horse');
    expect(await screen.findByTestId('library-page')).toBeInTheDocument();
    expect(fakeApi.callsTo('POST', '/api/v1/auth/login')[0]?.body).toEqual({
      username: 'alice',
      password: 'correct-horse', // secret-scan:allow (fake test value)
    });
  });

  it('returns to the page that required the login', async () => {
    fakeApi.on('POST', '/api/v1/auth/login', USER);
    fakeApi.on('GET', '/api/v1/items/abc', {
      id: 'abc',
      type: 'manga',
      title: 'Volta',
      format: 'cbz',
      page_count: 2,
      added_at: '2026-01-01T00:00:00Z',
      has_cover: false,
    });
    renderApp('/ler/abc');
    await fillAndSubmit('alice', 'correct-horse');
    expect(await screen.findByTestId('reader')).toBeInTheDocument();
  });

  it('shows ONE generic message for wrong credentials and clears the password', async () => {
    fakeApi.on('POST', '/api/v1/auth/login', apiError(401));
    renderApp('/');
    await fillAndSubmit('ghost-user', 'nope');
    const alert = await screen.findByTestId('login-error');
    expect(alert).toHaveTextContent('Usuário ou senha inválidos.');
    expect(alert.textContent).not.toMatch(/ghost-user|existe|não encontrado/i);
    expect(screen.getByTestId('login-password')).toHaveValue('');
    expect(screen.getByTestId('login-submit')).toBeDisabled(); // password empty again
  });

  it('handles 429 with a countdown from Retry-After and blocks resubmission', async () => {
    fakeApi.on('POST', '/api/v1/auth/login', rateLimited(30));
    renderApp('/');
    await fillAndSubmit();
    const alert = await screen.findByTestId('login-error');
    expect(alert).toHaveTextContent('Muitas tentativas. Tente novamente em 30 s.');
    expect(alert.textContent).not.toMatch(/alice|existe/i);

    const user = userEvent.setup();
    await user.type(screen.getByTestId('login-password'), 'another');
    expect(screen.getByTestId('login-submit')).toBeDisabled();
    expect(fakeApi.callsTo('POST', '/api/v1/auth/login')).toHaveLength(1);
  });

  it('counts the 429 wait down and re-enables the form at zero', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });
    fakeApi.on('POST', '/api/v1/auth/login', rateLimited(3));
    renderApp('/');
    await fillAndSubmit();
    expect(await screen.findByTestId('login-error')).toHaveTextContent('em 3 s');
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(screen.getByTestId('login-error')).toHaveTextContent('em 2 s');
    await act(async () => {
      vi.advanceTimersByTime(2500);
    });
    await waitFor(() => expect(screen.queryByTestId('login-error')).not.toBeInTheDocument());
    await userEvent.setup().type(screen.getByTestId('login-password'), 'x');
    expect(screen.getByTestId('login-submit')).toBeEnabled();
  });

  it('handles 503 (busy) with the Retry-After wait', async () => {
    const { ApiError } = await import('../../src/shared/api-client');
    fakeApi.on('POST', '/api/v1/auth/login', () => {
      throw new ApiError(503, 'busy', 2);
    });
    renderApp('/');
    await fillAndSubmit();
    expect(await screen.findByTestId('login-error')).toHaveTextContent(
      'Servidor ocupado. Tente novamente em 2 s.',
    );
  });

  it('shows a loading state on the button while the request is in flight', async () => {
    let release: (value: unknown) => void = () => undefined;
    fakeApi.on('POST', '/api/v1/auth/login', () => new Promise((resolve) => (release = resolve)));
    renderApp('/');
    await fillAndSubmit('alice', 'pw');
    expect(screen.getByTestId('login-submit')).toHaveTextContent('Entrando');
    expect(screen.getByTestId('login-submit')).toBeDisabled();
    await act(async () => release(USER));
    expect(await screen.findByTestId('library-page')).toBeInTheDocument();
  });
});

describe('safeRedirect', () => {
  it.each([
    ['/ler/abc', '/ler/abc'],
    ['/ajustes?x=1', '/ajustes?x=1'],
    ['//evil.example', '/'],
    ['https://evil.example', '/'],
    ['/\\evil', '/'],
    ['/login', '/'],
    ['/\t/evil.example', '/'],
    ['/ok\nnext', '/'],
    ['/ok\rnext', '/'],
    ['/a b', '/'],
    ['/a\u0000b', '/'],
    [undefined, '/'],
    [42, '/'],
  ])('%j -> %j', (input, expected) => {
    expect(safeRedirect(input)).toBe(expected);
  });
});
