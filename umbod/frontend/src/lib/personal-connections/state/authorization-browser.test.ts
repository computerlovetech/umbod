import { Window as TestWindow } from 'happy-dom';
import { InMemoryAttemptScheduler } from '../infrastructure/in-memory-attempt-scheduler';
import { describe, expect, test, vi } from 'vitest';
import type { DashboardApi } from '$lib/dashboard/api';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
import type { DashboardController } from '$lib/dashboard/state/port';
import { catalogue } from '$lib/dashboard/test-fixtures';
import type { PersonalConnectionsApi } from '../api';
import type { AuthorizationBrowser, AuthorizationWindow } from '../authorization-browser';
import { InMemoryAuthorizationBrowser } from '../infrastructure/in-memory-authorization-browser';
import { browserAuthorizationBrowser } from '../infrastructure/browser-authorization-browser';
import { InMemoryPersonalConnectionsApi } from '../infrastructure/in-memory-api';
import { authorizationHealth, completedAttempt, deferred, pendingAttempt, selection } from '../test-fixtures';
import { ConnectionState } from './connection-state.svelte';
import type { PersonalConnectionController } from './port';

function setup(browser?: AuthorizationBrowser): { api: PersonalConnectionsApi; state: PersonalConnectionController; memory: InMemoryAuthorizationBrowser } {
  const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
  const memory = new InMemoryAuthorizationBrowser();
  const state: PersonalConnectionController = new ConnectionState(selection, api, (): void => {}, undefined, browser ?? memory, new InMemoryAttemptScheduler());
  return { api, state, memory };
}

describe('explicit authorization browser ownership', () => {
  test('reserves synchronously before initiation and ignores duplicate starts', async (): Promise<void> => {
    const { api, state, memory } = setup();
    const pending = deferred<typeof pendingAttempt>();
    const start = vi.spyOn(api.authorization, 'start').mockImplementation(() => {
      expect(memory.windows).toHaveLength(1);
      expect(memory.windows[0].url).toBe('about:blank');
      expect(memory.windows[0].displayName).toBe(selection.display_name);
      return pending.promise;
    });
    const operation = state.start();
    expect(memory.windows).toHaveLength(1);
    await state.start();
    expect(start).toHaveBeenCalledOnce();
    pending.resolve(pendingAttempt);
    await operation;
    expect(memory.windows[0].url).toBe(pendingAttempt.authorization_url);
    expect(state.authorizationOpened).toBe(true);
    await state.start();
    expect(start).toHaveBeenCalledOnce();
    expect(memory.windows).toHaveLength(1);
    state.dispose();
  });

  test.each(['disabled', 'disposed', 'refreshing', 'uncertain', 'busy'] as const)('does not reserve when %s', async (guard): Promise<void> => {
    const { api, state, memory } = setup();
    let finish: (() => void) | undefined;
    let operation = Promise.resolve();
    if (guard === 'disabled') await state.setEnabled();
    if (guard === 'disposed') state.dispose();
    if (guard === 'refreshing') {
      vi.spyOn(api.authorization, 'getHealth').mockResolvedValue({ state: 'refreshing', deadline: '2030-01-01T00:00:00Z' });
      await state.loadHealth();
    }
    if (guard === 'uncertain') {
      vi.spyOn(api.connections, 'setEnablement').mockRejectedValue(new Error('Unavailable'));
      await state.setEnabled();
    }
    if (guard === 'busy') {
      const pending = deferred<void>();
      finish = (): void => pending.resolve();
      vi.spyOn(api.authorization, 'renew').mockImplementation(async () => {
        await pending.promise;
        return { status: 'refreshed', discovery_required: true };
      });
      await state.loadHealth();
      operation = state.renew();
    }
    const start = vi.spyOn(api.authorization, 'start');
    await state.start();
    expect(start).not.toHaveBeenCalled();
    expect(memory.windows).toHaveLength(0);
    finish?.();
    await operation;
    state.dispose();
  });

  test.each(['blocked', 'closed', 'failed', 'throwing', 'reserve-error'] as const)('retains manual fallback after %s browser interaction', async (mode): Promise<void> => {
    const memory = new InMemoryAuthorizationBrowser();
    const reserve = (): AuthorizationWindow | null => {
      if (mode === 'blocked') return null;
      if (mode === 'reserve-error') throw new Error('Browser unavailable');
      const reserved = memory.reserve(selection.display_name);
      if (mode === 'closed') reserved.close();
      if (mode === 'failed') vi.spyOn(reserved, 'navigate').mockReturnValue(false);
      if (mode === 'throwing') vi.spyOn(reserved, 'navigate').mockImplementation(() => { throw new Error('Navigation failed'); });
      return reserved;
    };
    const { api, state } = setup({ reserve });
    const start = vi.spyOn(api.authorization, 'start');
    await state.start();
    expect(state.attempt?.status).toBe('pending');
    expect(state.authorizationUrl).toBe('https://provider.example/authorize');
    expect(state.authorizationOpened).toBe(false);
    expect(state.error).toBe('');
    expect(state.needsRefresh).toBe(false);
    expect(memory.windows.every((popup) => popup.closed)).toBe(true);
    await state.start();
    expect(start).toHaveBeenCalledOnce();
    state.dispose();
  });

  test('health reads and manual status checks never reserve another window', async (): Promise<void> => {
    const { state, memory } = setup();
    await state.loadHealth();
    await state.refresh();
    expect(memory.windows).toHaveLength(0);
    await state.start();
    await state.check();
    await state.refresh();
    expect(memory.windows).toHaveLength(1);
    expect(state.authorizationOpened).toBe(true);
    state.dispose();
  });

  test('closes the blank reservation on initiation failure', async (): Promise<void> => {
    const { api, state, memory } = setup();
    vi.spyOn(api.authorization, 'start').mockRejectedValue(new Error('Unavailable'));
    await state.start();
    expect(memory.windows[0].closed).toBe(true);
    expect(state.attempt).toBeNull();
    expect(state.authorizationOpened).toBe(false);
    expect(state.needsRefresh).toBe(true);
  });

  test('disposal closes a pending reservation and late initiation cannot navigate', async (): Promise<void> => {
    const { api, state, memory } = setup();
    const pending = deferred<typeof pendingAttempt>();
    vi.spyOn(api.authorization, 'start').mockReturnValue(pending.promise);
    const operation = state.start();
    const navigate = vi.spyOn(memory.windows[0], 'navigate');
    state.dispose();
    expect(memory.windows[0].closed).toBe(true);
    pending.resolve(pendingAttempt);
    await operation;
    expect(navigate).not.toHaveBeenCalled();
    expect(state.attempt).toBeNull();
  });

  test.each(['cancel', 'complete', 'disable', 'disconnect', 'dispose', 'external-disable'] as const)('cleans up the owned popup on %s', async (action): Promise<void> => {
    const { api, state, memory } = setup();
    await state.start();
    if (action === 'cancel') await state.cancel();
    if (action === 'complete') {
      vi.spyOn(api.authorization, 'get').mockResolvedValue(completedAttempt);
      await state.check();
    }
    if (action === 'disable') await state.setEnabled();
    if (action === 'disconnect') {
      state.requestDisconnect();
      await state.disconnect();
    }
    if (action === 'dispose') state.dispose();
    if (action === 'external-disable') await state.reconcileSelection({ ...selection, enabled: false });
    expect(memory.windows[0].closed).toBe(true);
    expect(state.authorizationOpened).toBe(false);
    expect(state.authorizationUrl).toBe('');
    expect(state.attempt).toBeNull();
  });

  test('an already terminal initiation closes its unused reservation', async (): Promise<void> => {
    const { api, state, memory } = setup();
    vi.spyOn(api.authorization, 'start').mockResolvedValue({ ...pendingAttempt, status: 'failed' });
    await state.start();
    expect(memory.windows[0].url).toBe('about:blank');
    expect(memory.windows[0].closed).toBe(true);
    expect(state.authorizationOpened).toBe(false);
  });

  test('detail switches retain ownership, while owner replacement closes only owned windows', async (): Promise<void> => {
    const { api, memory } = setup();
    const unrelated = memory.reserve('Unrelated');
    const dashboardApi: DashboardApi = new InMemoryDashboardApi(catalogue);
    const page: DashboardController = new DashboardState(dashboardApi, api, memory, new InMemoryAttemptScheduler());
    await page.loadCatalogue();
    page.selectConnector('downstream_mcp:calendar');
    expect(page.selectedId).toBe('downstream_mcp:calendar');
    const state: PersonalConnectionController = page.personalCards[0];
    await state.start();
    page.selectConnector('downstream_mcp:shared');
    expect(page.selectedId).toBe('downstream_mcp:shared');
    await page.refreshOnFocus();
    expect(page.personalCards[0]).toBe(state);
    expect(state.authorizationOpened).toBe(true);
    expect(memory.windows[1].closed).toBe(false);
    vi.spyOn(dashboardApi.catalogue, 'list').mockResolvedValue({ ...catalogue, identity_key: 'other-owner' });
    await page.loadCatalogue();
    expect(memory.windows[1].closed).toBe(true);
    expect(memory.windows[0].closed).toBe(false);
    expect(state.authorizationUrl).toBe('');
    page.dispose();
    unrelated.close();
  });
});

describe('authorization browser adapter contract', () => {
  test.each(['http://provider.example', 'https://user:password@provider.example', 'javascript:alert(1)'])('in-memory windows reject unsafe URL %s', (url): void => {
    const browser: AuthorizationBrowser = new InMemoryAuthorizationBrowser();
    const popup = browser.reserve(selection.display_name);
    expect(popup?.navigate(url)).toBe(false);
    popup?.close();
  });

  test('real factory is lazy and detaches its blank window before validated navigation', (): void => {
    const browser: AuthorizationBrowser = browserAuthorizationBrowser();
    const replace = vi.fn<(url: string) => void>();
    const close = vi.fn<() => void>();
    const popup = { opener: {}, closed: false, document: new TestWindow().document, location: { replace }, close };
    const open = vi.fn<() => Window>().mockReturnValue(popup as unknown as Window);
    vi.stubGlobal('window', { open, matchMedia: () => ({ matches: false }), screen: { availWidth: 1920, availHeight: 1080 }, screenX: 100, screenY: 50, outerWidth: 1200, outerHeight: 900 });
    try {
      expect(open).not.toHaveBeenCalled();
      const reserved = browser.reserve(selection.display_name);
      expect(open).toHaveBeenCalledExactlyOnceWith('about:blank', '_blank', 'popup=yes,width=520,height=680,left=440,top=160');
      expect(popup.opener).toBeNull();
      expect(popup.document.title).toBe('Connecting to Calendar · Umbod');
      expect(popup.document.body.textContent).toContain('Connecting to Calendar…');
      expect(popup.document.querySelector('[role="status"]')).not.toBeNull();
      expect(reserved?.navigate('https://user@provider.example')).toBe(false);
      expect(replace).not.toHaveBeenCalled();
      expect(reserved?.navigate(pendingAttempt.authorization_url)).toBe(true);
      expect(replace).toHaveBeenCalledWith(pendingAttempt.authorization_url);
      popup.closed = true;
      expect(reserved?.navigate(pendingAttempt.authorization_url)).toBe(false);
      reserved?.close();
      expect(close).toHaveBeenCalledOnce();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
