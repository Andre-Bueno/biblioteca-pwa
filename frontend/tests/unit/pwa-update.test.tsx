import { act, fireEvent, renderHook, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { registerServiceWorker } from '../../src/app/registerServiceWorker';
import {
  flushAllProgress,
  registerProgressFlusher,
  useProgressSaver,
} from '../../src/shared/progress';
import { markNeedRefresh, resetPwaUpdate } from '../../src/shared/pwa';
import { fakeApi, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

const mocks = vi.hoisted(() => ({
  registerSW: vi.fn(),
  updateSW: vi.fn(),
}));
vi.mock('virtual:pwa-register', () => ({ registerSW: mocks.registerSW }));
vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

type RegisterOptions = { immediate?: boolean; onNeedRefresh?: () => void };
const registered = (): RegisterOptions => mocks.registerSW.mock.calls.at(-1)![0] as RegisterOptions;

describe('service worker update prompt', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
    resetPwaUpdate();
    mocks.registerSW.mockReset();
    mocks.updateSW.mockReset();
    mocks.updateSW.mockResolvedValue(undefined);
    mocks.registerSW.mockReturnValue(mocks.updateSW);
  });
  afterEach(() => vi.useRealTimers());

  it('registers in prompt mode and does nothing when disabled', () => {
    registerServiceWorker(false);
    expect(mocks.registerSW).not.toHaveBeenCalled();
    registerServiceWorker(true);
    expect(registered().immediate).toBe(true);
    expect(typeof registered().onNeedRefresh).toBe('function');
  });

  it('shows nothing until a new worker is waiting, and never reloads by itself', async () => {
    registerServiceWorker(true);
    renderApp('/');
    await screen.findByTestId('library-page');
    expect(screen.queryByTestId('app-update')).not.toBeInTheDocument();
    act(() => registered().onNeedRefresh?.());
    expect(await screen.findByTestId('app-update')).toHaveTextContent(
      'Nova versão do app disponível.',
    );
    expect(mocks.updateSW).not.toHaveBeenCalled();
  });

  it('"Recarregar" flushes pending reading progress first, then activates the worker (reload)', async () => {
    const order: string[] = [];
    registerProgressFlusher(async () => {
      order.push('flush');
    });
    mocks.updateSW.mockImplementation(async (reload?: boolean) => {
      order.push(`update:${String(reload)}`);
    });
    registerServiceWorker(true);
    renderApp('/');
    act(() => registered().onNeedRefresh?.());
    fireEvent.click(await screen.findByTestId('app-update-reload'));
    await vi.waitFor(() => expect(mocks.updateSW).toHaveBeenCalledTimes(1));
    expect(order).toEqual(['flush', 'update:true']);
  });

  it('a flush that hangs does not block the reload for more than ~2 s', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    registerProgressFlusher(() => new Promise(() => undefined));
    registerServiceWorker(true);
    renderApp('/');
    act(() => registered().onNeedRefresh?.());
    fireEvent.click(await screen.findByTestId('app-update-reload'));
    expect(mocks.updateSW).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(mocks.updateSW).toHaveBeenCalledWith(true);
  });

  it('"Depois" hides the prompt without reloading', async () => {
    registerServiceWorker(true);
    renderApp('/');
    act(() => registered().onNeedRefresh?.());
    fireEvent.click(await screen.findByTestId('app-update-later'));
    expect(screen.queryByTestId('app-update')).not.toBeInTheDocument();
    expect(mocks.updateSW).not.toHaveBeenCalled();
  });

  it('inside a reader only a small indicator shows, and the user chooses', async () => {
    fakeApi.on('GET', '/api/v1/items/m-1', {
      id: 'm-1',
      type: 'manga',
      title: 'M',
      format: 'cbz',
      page_count: 3,
      added_at: 'x',
      has_cover: false,
    });
    registerServiceWorker(true);
    renderApp('/ler/m-1');
    act(() => registered().onNeedRefresh?.());
    const pill = await screen.findByTestId('app-update-pill');
    expect(screen.queryByTestId('app-update')).not.toBeInTheDocument();
    expect(mocks.updateSW).not.toHaveBeenCalled();
    fireEvent.click(pill);
    expect(screen.getByTestId('app-update')).toBeInTheDocument();
  });

  it('works if the worker was already waiting before the screen mounted', async () => {
    act(() => markNeedRefresh());
    renderApp('/');
    expect(await screen.findByTestId('app-update')).toBeInTheDocument();
  });
});

describe('flushing reading progress', () => {
  beforeEach(() => {
    fakeApi.reset();
    fakeApi.on('PUT', '/api/v1/progress/item-9', ({ body }) => body);
  });

  it('flushAllProgress sends the pending position of a mounted reader right away', async () => {
    const { result, unmount } = renderHook(() => useProgressSaver('item-9'));
    act(() => result.current.report(7));
    expect(fakeApi.callsTo('PUT', '/api/v1/progress/item-9')).toHaveLength(0); // debounced
    await act(async () => {
      await flushAllProgress();
    });
    const puts = fakeApi.callsTo('PUT', '/api/v1/progress/item-9');
    expect(puts).toHaveLength(1);
    expect(puts[0]!.body).toEqual({ locator: 7 });
    unmount();
  });

  it('never rejects, even when a flusher throws', async () => {
    const unregister = registerProgressFlusher(() => Promise.reject(new Error('x')));
    await expect(flushAllProgress()).resolves.toBeUndefined();
    unregister();
  });
});

describe('PWA configuration', () => {
  const config = readFileSync('vite.config.ts', 'utf8');

  it('prompts instead of auto-updating, with no automatic skipWaiting or API caching', () => {
    expect(config).toContain("registerType: 'prompt'");
    expect(config).not.toContain('autoUpdate');
    expect(config).toContain('skipWaiting: false');
    expect(config).toContain('runtimeCaching: []');
    expect(config).toContain('/^\\/api\\//');
  });
});
