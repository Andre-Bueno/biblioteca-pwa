import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, NetworkError, RateLimitError } from '../../src/shared/api-client/errors';
import { ProtectedImage } from '../../src/shared/ui';
import { resetImageRecovery } from '../../src/shared/ui/useImageRecovery';
import { USER, apiError, fakeApi, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

describe('session check at start-up', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it.each([
    ['429', () => new RateLimitError(30)],
    ['503', () => new ApiError(503, 'busy', 2)],
    ['offline', () => new NetworkError()],
  ])('%s keeps the user out of the login and offers a retry', async (_name, makeError) => {
    let attempts = 0;
    fakeApi.on('GET', '/api/v1/auth/me', () => {
      attempts += 1;
      if (attempts === 1) throw makeError();
      return USER;
    });
    renderApp('/');
    const box = await screen.findByTestId('session-error');
    expect(box).toHaveTextContent('Não foi possível verificar a sessão');
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByTestId('session-retry'));
    expect(await screen.findByTestId('library-page')).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it('only a 401 means signed out', async () => {
    fakeApi.on('GET', '/api/v1/auth/me', apiError(401));
    renderApp('/');
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('session-error')).not.toBeInTheDocument();
  });
});

describe('ProtectedImage session recovery', () => {
  beforeEach(() => {
    fakeApi.reset();
    resetImageRecovery();
  });

  it('refreshes the session (not /auth/me) once, remounts, then offers a manual retry', async () => {
    render(<ProtectedImage src="/api/v1/items/a/cover" alt="Capa" testId="img" />);
    fireEvent.error(screen.getByTestId('img'));
    await waitFor(() => expect(fakeApi.api.refreshSession).toHaveBeenCalledTimes(1));
    expect(fakeApi.callsTo('GET', '/api/v1/auth/me')).toHaveLength(0);

    const second = await screen.findByTestId('img');
    expect(second).toHaveAttribute('data-state', 'loading');
    fireEvent.error(second);
    expect(await screen.findByRole('button', { name: /tentar novamente/i })).toBeInTheDocument();
    expect(fakeApi.api.refreshSession).toHaveBeenCalledTimes(1);
  });

  it('images failing together share ONE recovery attempt', async () => {
    render(
      <>
        <ProtectedImage src="/a" alt="a" testId="a" />
        <ProtectedImage src="/b" alt="b" testId="b" />
        <ProtectedImage src="/c" alt="c" testId="c" />
      </>,
    );
    for (const id of ['a', 'b', 'c']) fireEvent.error(screen.getByTestId(id));
    await waitFor(() => expect(screen.getByTestId('a')).toHaveAttribute('data-state', 'loading'));
    expect(fakeApi.api.refreshSession).toHaveBeenCalledTimes(1);
  });

  it('does not touch the session when another image just loaded (404/422 are not session errors)', async () => {
    render(
      <>
        <ProtectedImage src="/ok" alt="ok" testId="ok" />
        <ProtectedImage src="/missing" alt="missing" testId="missing" />
      </>,
    );
    fireEvent.load(screen.getByTestId('ok'));
    fireEvent.error(screen.getByTestId('missing'));
    expect(await screen.findByRole('button', { name: /tentar novamente/i })).toBeInTheDocument();
    expect(fakeApi.api.refreshSession).not.toHaveBeenCalled();
  });

  it('allows at most one recovery per window, even for later errors', async () => {
    const { unmount } = render(<ProtectedImage src="/a" alt="a" testId="a" />);
    fireEvent.error(screen.getByTestId('a'));
    await waitFor(() => expect(fakeApi.api.refreshSession).toHaveBeenCalledTimes(1));
    unmount();

    render(<ProtectedImage src="/b" alt="b" testId="b" />);
    fireEvent.error(screen.getByTestId('b'));
    expect(await screen.findByRole('button', { name: /tentar novamente/i })).toBeInTheDocument();
    expect(fakeApi.api.refreshSession).toHaveBeenCalledTimes(1);
  });

  it('marks the image as loaded', () => {
    render(<ProtectedImage src="/x" alt="x" testId="img" />);
    fireEvent.load(screen.getByTestId('img'));
    expect(screen.getByTestId('img')).toHaveAttribute('data-state', 'loaded');
  });
});
