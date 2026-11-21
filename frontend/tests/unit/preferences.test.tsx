import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../src/shared/api-client/errors';
import { fakeApi, signedIn } from '../helpers/fake-api';
import { renderApp } from '../helpers/render-app';

vi.mock('../../src/shared/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/shared/api-client')>();
  const { fakeApi: fake } = await import('../helpers/fake-api');
  return { ...actual, apiClient: fake.api };
});

const puts = () => fakeApi.callsTo('PUT', '/api/v1/me/preferences');
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe('preferences: never overwrite the server with defaults', () => {
  beforeEach(() => {
    fakeApi.reset();
    signedIn();
  });

  it('a failed GET + theme change does not write the default reading direction', async () => {
    let getAttempts = 0;
    fakeApi.on('GET', '/api/v1/me/preferences', () => {
      getAttempts += 1;
      if (getAttempts === 1) throw new ApiError(503, 'busy');
      return { theme: 'light', reading_direction: 'vertical' };
    });
    renderApp('/ajustes');
    const user = userEvent.setup();
    expect(await screen.findByTestId('preferences-load-error')).toBeInTheDocument();

    await user.click(screen.getByTestId('theme-toggle-dark'));
    expect(document.documentElement.dataset.theme).toBe('dark'); // applied locally
    await wait(100);
    expect(puts()).toHaveLength(0); // nothing built from defaults

    await user.click(screen.getByRole('button', { name: /tentar de novo/i }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    // Full object: the user's edit on top of the SERVER data (vertical stays vertical).
    expect(puts()[0]!.body).toEqual({ theme: 'dark', reading_direction: 'vertical' });
    await waitFor(() =>
      expect(screen.getByTestId('reading-direction-vertical')).toHaveAttribute(
        'aria-pressed',
        'true',
      ),
    );
    expect(screen.queryByTestId('preferences-load-error')).not.toBeInTheDocument();
  });

  it('an edit made while the GET is still pending is merged into the server data', async () => {
    let release: (value: unknown) => void = () => undefined;
    fakeApi.on(
      'GET',
      '/api/v1/me/preferences',
      () => new Promise((resolve) => (release = resolve)),
    );
    renderApp('/ajustes');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('theme-toggle-dark'));
    expect(puts()).toHaveLength(0);
    release({ theme: 'light', reading_direction: 'vertical' });
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0]!.body).toEqual({ theme: 'dark', reading_direction: 'vertical' });
  });

  it('serializes PUTs: one in flight, in order, the last value wins', async () => {
    const releases: ((value: unknown) => void)[] = [];
    let active = 0;
    let maxActive = 0;
    fakeApi.on('PUT', '/api/v1/me/preferences', ({ body }) => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      return new Promise((resolve) =>
        releases.push(() => {
          active -= 1;
          resolve(body);
        }),
      );
    });
    renderApp('/ajustes');
    const user = userEvent.setup();
    await user.click(await screen.findByTestId('reading-direction-ltr'));
    await user.click(screen.getByTestId('reading-direction-vertical'));
    await user.click(screen.getByTestId('reading-direction-rtl'));

    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0]!.body).toMatchObject({ reading_direction: 'ltr' });
    expect(releases).toHaveLength(1); // the others wait for the one in flight

    releases[0]!(undefined);
    await waitFor(() => expect(puts()).toHaveLength(2));
    expect(puts()[1]!.body).toMatchObject({ reading_direction: 'rtl' }); // newest value only
    releases[1]!(undefined);
    await wait(50);
    expect(puts()).toHaveLength(2);
    expect(maxActive).toBe(1);
  });
});
