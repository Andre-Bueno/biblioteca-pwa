import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { USER, apiError, fakeApi, rateLimited, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const prefPuts = () => fakeApi.callsTo('PUT', '/api/v1/me/preferences');

describe('settings: preferences and theme', () => {
  beforeEach(() => {
    fakeApi.reset();
    delete document.documentElement.dataset.theme;
    signedIn();
  });

  it('applies the saved theme as soon as the session loads', async () => {
    fakeApi.on('GET', '/api/v1/auth/me', { ...USER, theme_pref: 'dark' });
    fakeApi.on('GET', '/api/v1/me/preferences', { theme: 'dark', reading_direction: 'ltr' });
    renderApp('/');
    await screen.findByTestId('library-page');
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
  });

  it('changes the theme immediately and saves it on the server', async () => {
    let release: (value: unknown) => void = () => undefined;
    fakeApi.on(
      'PUT',
      '/api/v1/me/preferences',
      () => new Promise((resolve) => (release = resolve)),
    );
    renderApp('/ajustes');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('theme-toggle-dark'));
    expect(document.documentElement.dataset.theme).toBe('dark'); // before the server answers
    expect(prefPuts()[0]!.body).toEqual({ theme: 'dark', reading_direction: 'rtl' });
    release({ theme: 'dark', reading_direction: 'rtl' });
  });

  it('saves the reading direction and shows it selected', async () => {
    renderApp('/ajustes');
    const user = userEvent.setup();
    expect(await screen.findByTestId('reading-direction-rtl')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await user.click(screen.getByTestId('reading-direction-vertical'));
    expect(screen.getByTestId('reading-direction-vertical')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(prefPuts().at(-1)!.body).toEqual({ theme: 'system', reading_direction: 'vertical' });
  });

  it('warns when saving fails but keeps the local choice', async () => {
    fakeApi.on('PUT', '/api/v1/me/preferences', apiError(500));
    renderApp('/ajustes');
    await userEvent.setup().click(await screen.findByTestId('theme-toggle-light'));
    expect(await screen.findByTestId('preferences-error')).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('ignores malformed preference values from the server', async () => {
    fakeApi.on('GET', '/api/v1/me/preferences', { theme: 'neon', reading_direction: 42 });
    renderApp('/ajustes');
    expect(await screen.findByTestId('reading-direction-rtl')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('signs out and returns to the login', async () => {
    fakeApi.on('POST', '/api/v1/auth/logout', undefined);
    renderApp('/ajustes');
    await userEvent.setup().click(await screen.findByTestId('logout'));
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(fakeApi.callsTo('POST', '/api/v1/auth/logout')).toHaveLength(1);
  });

  it('signs out locally even if the server call fails', async () => {
    fakeApi.on('POST', '/api/v1/auth/logout', apiError(500));
    renderApp('/ajustes');
    await userEvent.setup().click(await screen.findByTestId('logout'));
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
  });
});

describe('settings: change password', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  async function fill(current: string, next: string, confirm: string) {
    const user = userEvent.setup();
    await user.type(await screen.findByTestId('password-current'), current);
    await user.type(screen.getByTestId('password-new'), next);
    await user.type(screen.getByTestId('password-confirm'), confirm);
    await user.click(screen.getByTestId('password-submit'));
  }
  const posts = () => fakeApi.callsTo('POST', '/api/v1/auth/change-password');

  it('changes the password and clears the fields', async () => {
    fakeApi.on('POST', '/api/v1/auth/change-password', undefined);
    renderApp('/ajustes');
    await fill('old-pass', 'new-pass-123', 'new-pass-123');
    expect(await screen.findByTestId('password-feedback')).toHaveTextContent('Senha alterada');
    expect(posts()[0]!.body).toEqual({
      current_password: 'old-pass',
      new_password: 'new-pass-123',
    });
    expect(screen.getByTestId('password-current')).toHaveValue('');
  });

  it('does not call the server when the confirmation differs', async () => {
    renderApp('/ajustes');
    await fill('old-pass', 'new-pass-123', 'different');
    expect(await screen.findByTestId('password-feedback')).toHaveTextContent('confirmação');
    expect(posts()).toHaveLength(0);
  });

  it.each([
    [401, 'senha atual está incorreta'],
    [403, 'senha atual está incorreta'],
    [422, 'requisitos'],
  ])('maps %i to a clear message', async (status, text) => {
    fakeApi.on('POST', '/api/v1/auth/change-password', apiError(status));
    renderApp('/ajustes');
    await fill('old-pass', 'new-pass-123', 'new-pass-123');
    expect(await screen.findByTestId('password-feedback')).toHaveTextContent(text);
  });

  it('blocks further attempts during a 429 wait', async () => {
    fakeApi.on('POST', '/api/v1/auth/change-password', rateLimited(20));
    renderApp('/ajustes');
    await fill('old-pass', 'new-pass-123', 'new-pass-123');
    expect(await screen.findByTestId('password-feedback')).toHaveTextContent('Muitas tentativas');
    expect(screen.getByTestId('password-submit')).toBeDisabled();
  });
});
