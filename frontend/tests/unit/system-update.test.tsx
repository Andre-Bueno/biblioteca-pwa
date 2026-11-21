import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, NetworkError } from '../../src/shared/api-client/errors';
import { reloadPage } from '../../src/shared/system';
import { apiError, fakeApi, rateLimited, signedIn, USER } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});
vi.mock('../../src/shared/system/reload', () => ({ reloadPage: vi.fn() }));

const VERSION = '/api/v1/system/version';
const CHECK = '/api/v1/system/update/check';
const UPDATE = '/api/v1/system/update';

const INFO = {
  current: '1.2.3',
  update_available: true,
  latest: {
    tag: 'v1.3.0',
    version: '1.3.0',
    name: 'Versao 1.3.0',
    notes: 'Novidades\n- item um\n- item dois',
    published_at: '2026-11-20T10:00:00Z',
    url: 'https://github.com/dono/app/releases/tag/v1.3.0',
  },
  checked_at: '2026-11-21T10:00:00Z',
  webhook_configured: true,
  update: { state: 'idle', tag: null, requested_at: null },
};

function setup(options: { admin?: boolean; info?: unknown; route?: string } = {}) {
  signedIn();
  const admin = options.admin ?? true;
  fakeApi.on('GET', '/api/v1/auth/me', { ...USER, role: admin ? 'admin' : 'user' });
  fakeApi.on('GET', VERSION, (options.info ?? INFO) as object);
  fakeApi.on('POST', UPDATE, ({ body }) => ({
    state: 'requested',
    tag: (body as { tag: string }).tag,
    requested_at: '2026-11-21T11:00:00Z',
  }));
  return renderApp(options.route ?? '/');
}

const versionGets = () => fakeApi.callsTo('GET', VERSION).length;
const updatePosts = () => fakeApi.callsTo('POST', UPDATE);
const advance = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

async function startUpdate() {
  fireEvent.click(await screen.findByTestId('update-now'));
  fireEvent.click(await screen.findByTestId('update-confirm-yes'));
}

describe('version notice: who sees it', () => {
  beforeEach(() => fakeApi.reset());

  it('a regular user never sees the notice (and no admin controls in the settings)', async () => {
    setup({ admin: false, info: { current: '1.2.3', update_available: true }, route: '/ajustes' });
    expect(await screen.findByTestId('app-version')).toHaveTextContent('Versão do app: 1.2.3');
    expect(screen.queryByTestId('update-notice')).not.toBeInTheDocument();
    expect(screen.queryByTestId('check-updates')).not.toBeInTheDocument();
  });

  it('an admin sees the notice on the library, with current and new version', async () => {
    setup();
    expect(await screen.findByTestId('update-message')).toHaveTextContent(
      'Nova versão v1.3.0 disponível (atual 1.2.3)',
    );
  });

  it('and on the settings', async () => {
    setup({ route: '/ajustes' });
    expect(await screen.findByTestId('update-message')).toBeInTheDocument();
  });

  it('no notice when there is no update, or when the version call fails (silently)', async () => {
    setup({ info: { ...INFO, update_available: false } });
    await screen.findByTestId('library-page');
    await waitFor(() => expect(versionGets()).toBe(1));
    expect(screen.queryByTestId('update-notice')).not.toBeInTheDocument();
  });

  it('a failing version call shows nothing and does not retry in a loop', async () => {
    signedIn();
    fakeApi.on('GET', VERSION, apiError(500));
    renderApp('/');
    await screen.findByTestId('library-page');
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(versionGets()).toBe(1);
    expect(screen.queryByTestId('update-notice')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('"Agora não" hides it until the page is reloaded (also on the other screen)', async () => {
    setup();
    fireEvent.click(await screen.findByTestId('update-dismiss'));
    expect(screen.queryByTestId('update-notice')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('open-settings'));
    await screen.findByTestId('settings-page');
    expect(screen.queryByTestId('update-notice')).not.toBeInTheDocument();
  });
});

describe('version notice: release notes and links', () => {
  beforeEach(() => fakeApi.reset());

  it('"Ver novidades" shows the notes as plain text and an https GitHub link', async () => {
    setup();
    const toggle = await screen.findByTestId('update-notes-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('update-notes')).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const notes = screen.getByTestId('update-notes');
    expect(notes.tagName).toBe('PRE');
    expect(notes.textContent).toBe('Novidades\n- item um\n- item dois');
    const link = screen.getByTestId('update-github');
    expect(link).toHaveAttribute('href', 'https://github.com/dono/app/releases/tag/v1.3.0');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveTextContent('Abrir no GitHub');
  });

  it('hostile HTML in the notes stays text: no element is created', async () => {
    const hostile = '<img src=x onerror=alert(1)><script>alert(2)</script><b>forte</b>';
    setup({ info: { ...INFO, latest: { ...INFO.latest, notes: hostile } } });
    fireEvent.click(await screen.findByTestId('update-notes-toggle'));
    const notes = screen.getByTestId('update-notes');
    expect(notes.textContent).toBe(hostile);
    expect(notes.children).toHaveLength(0);
    expect(document.querySelector('img[src="x"], script, b')).toBeNull();
  });

  it('a hostile tag/name is text too', async () => {
    setup({ info: { ...INFO, latest: { ...INFO.latest, tag: 'v1<i>x</i>' } } });
    const message = await screen.findByTestId('update-message');
    expect(message.textContent).toContain('v1<i>x</i>');
    expect(message.querySelector('i')).toBeNull();
  });

  it.each(['javascript:alert(1)', 'http://github.com/x', 'data:text/html,x', '//evil.com'])(
    'a non-https url (%s) gets no link',
    async (url) => {
      setup({ info: { ...INFO, latest: { ...INFO.latest, url } } });
      fireEvent.click(await screen.findByTestId('update-notes-toggle'));
      expect(screen.queryByTestId('update-github')).not.toBeInTheDocument();
      expect(screen.getByTestId('update-notice').querySelector('a')).toBeNull();
    },
  );

  it('long notes are clamped to 4000 characters', async () => {
    setup({ info: { ...INFO, latest: { ...INFO.latest, notes: 'x'.repeat(9000) } } });
    fireEvent.click(await screen.findByTestId('update-notes-toggle'));
    expect(screen.getByTestId('update-notes').textContent).toHaveLength(4000);
  });

  it('without a webhook: no "Atualizar agora", only the manual instruction and the link', async () => {
    setup({ info: { ...INFO, webhook_configured: false } });
    expect(await screen.findByTestId('update-manual')).toHaveTextContent('Atualize pelo servidor');
    expect(screen.queryByTestId('update-now')).not.toBeInTheDocument();
    const link = screen.getByTestId('update-manual-link');
    expect(link).toHaveAttribute('href', INFO.latest.url);
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});

describe('version notice: updating', () => {
  beforeEach(() => {
    fakeApi.reset();
    vi.mocked(reloadPage).mockClear();
  });
  afterEach(() => vi.useRealTimers());

  it('asks for confirmation first and only then POSTs the exact tag', async () => {
    setup();
    fireEvent.click(await screen.findByTestId('update-now'));
    const dialog = screen.getByRole('dialog', { name: 'Confirmar atualização' });
    expect(dialog).toHaveTextContent('O app será reiniciado por alguns instantes. Continuar?');
    expect(updatePosts()).toHaveLength(0);
    fireEvent.click(screen.getByTestId('update-confirm-no')); // cancel: still nothing sent
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(updatePosts()).toHaveLength(0);

    fireEvent.click(screen.getByTestId('update-now'));
    fireEvent.click(screen.getByTestId('update-confirm-yes'));
    expect(await screen.findByTestId('update-progress')).toHaveTextContent(
      'Atualizando para 1.3.0',
    );
    expect(updatePosts()).toHaveLength(1);
    expect(updatePosts()[0]!.body).toEqual({ tag: 'v1.3.0' });
  });

  it('Esc closes the confirmation without sending anything', async () => {
    setup();
    fireEvent.click(await screen.findByTestId('update-now'));
    await userEvent.setup().keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(updatePosts()).toHaveLength(0);
  });

  it.each([
    [503, 'não está configurado'],
    [502, 'Não foi possível acionar'],
    [403, 'Não foi possível solicitar'],
  ])('a %i answer gives a friendly message and keeps the buttons', async (status, text) => {
    setup();
    fakeApi.on('POST', UPDATE, apiError(status));
    await startUpdate();
    expect(await screen.findByTestId('update-error')).toHaveTextContent(text);
    expect(screen.getByTestId('update-now')).toBeInTheDocument();
    expect(screen.queryByTestId('update-progress')).not.toBeInTheDocument();
  });

  it('429 gives a "wait" message', async () => {
    setup();
    fakeApi.on('POST', UPDATE, rateLimited(30));
    await startUpdate();
    expect(await screen.findByTestId('update-error')).toHaveTextContent('Muitas tentativas');
  });

  it('409 (already requested) says so and follows the progress', async () => {
    setup();
    fakeApi.on('POST', UPDATE, () => {
      throw new ApiError(409, 'x');
    });
    await startUpdate();
    expect(await screen.findByTestId('update-error')).toHaveTextContent('já foi solicitada');
    expect(screen.getByTestId('update-progress')).toBeInTheDocument();
  });

  it('polls every 5 s (surviving network failures) until the version changes, then offers reload', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    setup({ info: INFO });
    await screen.findByTestId('update-message'); // the first call (when the app opened) got INFO
    fakeApi.on('GET', VERSION, () => {
      calls += 1; // polling calls only
      if (calls === 1) throw new NetworkError(); // the container is restarting
      if (calls === 2) return INFO; // still the old version
      return { current: '1.3.0', update_available: false };
    });
    await startUpdate();
    await screen.findByTestId('update-progress');
    expect(versionGets()).toBe(1);
    await advance(4000);
    expect(versionGets()).toBe(1); // not before 5 s
    await advance(1000);
    expect(versionGets()).toBe(2);
    expect(screen.getByTestId('update-progress')).toBeInTheDocument(); // failure tolerated
    await advance(5000);
    expect(screen.getByTestId('update-progress')).toBeInTheDocument();
    await advance(5000);
    expect(screen.getByTestId('update-done')).toHaveTextContent('Atualizado para 1.3.0');
    const reload = screen.getByTestId('update-reload');
    expect(reload).toHaveTextContent('Recarregar');
    fireEvent.click(reload);
    expect(reloadPage).toHaveBeenCalledTimes(1);
    const polled = versionGets();
    await advance(20000);
    expect(versionGets()).toBe(polled); // polling stopped
  });

  it('gives up after about 5 minutes and says the update continues on the server', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup();
    await startUpdate();
    await screen.findByTestId('update-progress');
    for (let i = 0; i < 60; i += 1) await advance(5000);
    expect(screen.getByTestId('update-progress')).toBeInTheDocument();
    await advance(5000);
    expect(screen.getByTestId('update-timeout')).toHaveTextContent('continua no servidor');
    const polled = versionGets();
    expect(polled).toBeLessThanOrEqual(61);
    await advance(30000);
    expect(versionGets()).toBe(polled);
  });

  it('stops polling when the notice leaves the screen', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const view = setup();
    await startUpdate();
    await screen.findByTestId('update-progress');
    await advance(5000);
    const polled = versionGets();
    expect(polled).toBeGreaterThan(1);
    view.unmount();
    await advance(60000);
    expect(versionGets()).toBe(polled);
  });

  it('resumes the progress if the server already reports a requested update', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup({ info: { ...INFO, update: { state: 'requested', tag: 'v1.3.0', requested_at: 'x' } } });
    expect(await screen.findByTestId('update-progress')).toBeInTheDocument();
    expect(updatePosts()).toHaveLength(0);
    await advance(5000);
    expect(versionGets()).toBe(2);
  });

  it('a failed state reported by the server stops the progress with a message', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup();
    await startUpdate();
    await screen.findByTestId('update-progress');
    fakeApi.on('GET', VERSION, {
      ...INFO,
      update: { state: 'failed', tag: 'v1.3.0', requested_at: 'x' },
    });
    await advance(5000);
    expect(screen.getByTestId('update-error')).toHaveTextContent('falhou no servidor');
    expect(screen.queryByTestId('update-progress')).not.toBeInTheDocument();
  });
});

describe('version polling', () => {
  beforeEach(() => fakeApi.reset());
  afterEach(() => {
    vi.useRealTimers();
    Reflect.deleteProperty(document, 'visibilityState');
  });

  it('asks again at most every 30 minutes while the tab is visible', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup();
    await screen.findByTestId('update-message');
    expect(versionGets()).toBe(1);
    await advance(29 * 60 * 1000);
    expect(versionGets()).toBe(1);
    await advance(61 * 1000);
    expect(versionGets()).toBe(2);
  });

  it('does not ask while the tab is hidden', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup();
    await screen.findByTestId('update-message');
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    await advance(31 * 60 * 1000);
    expect(versionGets()).toBe(1);
  });
});

describe('settings: version and manual check', () => {
  beforeEach(() => fakeApi.reset());
  afterEach(() => vi.useRealTimers());

  it('shows the version and "Verificar atualizações" for admins', async () => {
    setup({ route: '/ajustes' });
    expect(await screen.findByTestId('app-version')).toHaveTextContent('Versão do app: 1.2.3');
    fakeApi.on('POST', CHECK, { ...INFO, update_available: false, latest: null });
    fireEvent.click(screen.getByTestId('check-updates'));
    expect(await screen.findByText('Você está na versão mais recente.')).toBeInTheDocument();
    expect(fakeApi.callsTo('POST', CHECK)).toHaveLength(1);
  });

  it('a check that finds a release shows the notice', async () => {
    setup({ route: '/ajustes', info: { ...INFO, update_available: false, latest: null } });
    await screen.findByTestId('app-version');
    expect(screen.queryByTestId('update-notice')).not.toBeInTheDocument();
    fakeApi.on('POST', CHECK, INFO);
    fireEvent.click(screen.getByTestId('check-updates'));
    expect(await screen.findByTestId('update-message')).toBeInTheDocument();
    expect(screen.getByTestId('check-result')).toHaveTextContent('Nova versão disponível: v1.3.0');
  });

  it('the button is disabled while the request is in flight', async () => {
    setup({ route: '/ajustes' });
    let release: (value: unknown) => void = () => undefined;
    fakeApi.on('POST', CHECK, () => new Promise((resolve) => (release = resolve)));
    const button = await screen.findByTestId('check-updates');
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    expect(button).toHaveTextContent('Verificando');
    fireEvent.click(button);
    expect(fakeApi.callsTo('POST', CHECK)).toHaveLength(1);
    release({ ...INFO, update_available: false, latest: null });
    await waitFor(() => expect(button).toBeEnabled());
  });

  it('a 429 disables the button for the Retry-After time', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup({ route: '/ajustes' });
    fakeApi.on('POST', CHECK, rateLimited(30));
    const button = await screen.findByTestId('check-updates');
    fireEvent.click(button);
    expect(await screen.findByText(/Muitas verificações/)).toBeInTheDocument();
    expect(button).toBeDisabled();
    await advance(29000);
    expect(button).toBeDisabled();
    await advance(2000);
    expect(button).toBeEnabled();
  });

  it('any other failure is explained without blocking', async () => {
    setup({ route: '/ajustes' });
    fakeApi.on('POST', CHECK, apiError(502));
    const button = await screen.findByTestId('check-updates');
    fireEvent.click(button);
    expect(
      await within(screen.getByTestId('settings-page')).findByText(
        'Não foi possível verificar agora.',
      ),
    ).toBeInTheDocument();
    expect(button).toBeEnabled();
  });
});
