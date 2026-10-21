import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '../api';
import type { AuthorizationHealth, RenewalResult, Selection } from '../domain/schemas';
import { InMemoryPersonalConnectionsApi } from '../infrastructure/in-memory-api';
import { authorizationHealth, completedAttempt, deferred, selection } from '../test-fixtures';
import { ConnectionState } from './connection-state.svelte';
import { ConnectionsState } from './connections-state.svelte';

function setup(health: AuthorizationHealth = authorizationHealth): { api: PersonalConnectionsApi; card: ConnectionState } {
  const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: health });
  return { api, card: new ConnectionState(selection, api, vi.fn<() => void>()) };
}

const nonRenewable: AuthorizationHealth[] = [
  { state: 'not_authorized' }, { state: 'unsupported' },
  { state: 'authorized', expires_at: '2030-01-01T00:00:00Z', refresh_supported: false },
  { state: 'expired', expires_at: '2030-01-01T00:00:00Z', refresh_supported: false },
  { state: 'reconnect_required', reason: 'provider_rejected' },
  { state: 'reconnect_required', reason: 'refresh_denied' },
  { state: 'reconnect_required', reason: 'refresh_uncertain' },
  { state: 'refreshing', deadline: '2000-01-01T00:00:00Z' }
];

describe('authorization recovery through public state actions', () => {
  test.each(nonRenewable)('never renews $state without explicit capability', async (health: AuthorizationHealth): Promise<void> => {
    const { api, card } = setup(health);
    const renew = vi.spyOn(api.authorization, 'renew');
    await card.loadHealth();
    expect(card.canRenew).toBe(false);
    expect(card.canDiscover).toBe(health.state === 'authorized');
    await card.renew();
    expect(renew).not.toHaveBeenCalled();
  });

  test.each(['authorized', 'expired'] as const)('explicitly renews %s and reads facts without discovery', async (state): Promise<void> => {
    const { api, card } = setup({ state, expires_at: '2000-01-01T00:00:00Z', refresh_supported: true });
    const renew = vi.spyOn(api.authorization, 'renew');
    const health = vi.spyOn(api.authorization, 'getHealth');
    const get = vi.spyOn(api.connections, 'get');
    const discover = vi.spyOn(api.connections, 'discover');
    const enable = vi.spyOn(api.connections, 'setEnablement');
    await card.loadHealth();
    expect(renew).not.toHaveBeenCalled();
    expect(card.canRenew).toBe(true);
    await card.renew();
    expect(renew).toHaveBeenCalledExactlyOnceWith('calendar', {});
    expect(health).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenCalledOnce();
    expect(discover).not.toHaveBeenCalled();
    expect(enable).not.toHaveBeenCalled();
    expect(card.message).toBe('Authorization renewed. Discover tools before using them.');
    await card.discover();
    expect(discover).toHaveBeenCalledOnce();
    expect(health).toHaveBeenCalledTimes(3);
  });

  test('enablement, own attempts, pending renewal and uncertain outcomes separately gate renewal', async (): Promise<void> => {
    const { api, card } = setup();
    await card.loadHealth();
    await card.setEnabled();
    expect(card.canRenew).toBe(false);
    await card.setEnabled();
    await card.start();
    expect(card.canRenew).toBe(false);
    await card.cancel();
    expect(card.canRenew).toBe(true);
    const pending = deferred<RenewalResult>();
    const renew = vi.spyOn(api.authorization, 'renew').mockReturnValue(pending.promise);
    const renewing = card.renew();
    expect(card.canRenew).toBe(false);
    await card.renew();
    pending.reject(new NetworkError(new Error('private token')));
    await renewing;
    expect(renew).toHaveBeenCalledOnce();
    expect(card.needsRefresh).toBe(true);
    expect(card.canRenew).toBe(false);
    expect(card.error).toContain('Check authorization status');
    expect(card.error).not.toContain('private');
    expect(card.health).toEqual(authorizationHealth);
  });

  test('health 503 is unavailable, not expiry or rejection, and allows explicit sign-in and cleanup', async (): Promise<void> => {
    const { api, card } = setup();
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new HttpError(503, 'private', { detail: 'secret' }));
    const renew = vi.spyOn(api.authorization, 'renew');
    const discover = vi.spyOn(api.connections, 'discover');
    await card.loadHealth();
    expect(card.health).toBeNull();
    expect(card.healthPhase).toBe('unavailable');
    expect(card.selection.has_authorization).toBe(true);
    await card.renew();
    await card.discover();
    expect(renew).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    await card.start();
    expect(card.attempt?.status).toBe('pending');
    card.requestDisconnect();
    await card.disconnect();
    expect(card.selection.enabled).toBe(false);
  });

  test('refreshing deadline never authorizes a retry, sign-in or discovery', async (): Promise<void> => {
    const { api, card } = setup({ state: 'refreshing', deadline: '2000-01-01T00:00:00Z' });
    const start = vi.spyOn(api.authorization, 'start');
    await card.loadHealth();
    await card.start();
    expect(start).not.toHaveBeenCalled();
    expect(card.canDiscover).toBe(false);
    expect(card.canRenew).toBe(false);
  });

  test.each([409, 422, 503])('renewal %s never automatically retries or reads status', async (status): Promise<void> => {
    const { api, card } = setup();
    await card.loadHealth();
    const health = vi.spyOn(api.authorization, 'getHealth');
    const renew = vi.spyOn(api.authorization, 'renew').mockRejectedValue(new HttpError(status, 'secret', { detail: { code: 'personal_refresh_changed', text: 'secret' } }));
    await card.renew();
    await card.renew();
    expect(renew).toHaveBeenCalledOnce();
    expect(health).not.toHaveBeenCalled();
    expect(card.error).not.toContain('secret');
    expect(card.needsRefresh).toBe(true);
    health.mockRejectedValueOnce(new NetworkError('secret'));
    await card.refresh();
    expect(card.needsRefresh).toBe(true);
    expect(card.healthPhase).toBe('unavailable');
    await card.refresh();
    expect(card.needsRefresh).toBe(false);
    expect(renew).toHaveBeenCalledOnce();
  });

  test.each(['failed', 'cancelled', 'expired'] as const)('replacement %s preserves previous grant and health', async (status): Promise<void> => {
    const { api, card } = setup();
    await card.loadHealth();
    await card.start();
    expect(card.health).toEqual(authorizationHealth);
    vi.spyOn(api.authorization, 'get').mockResolvedValue({ ...completedAttempt, status });
    await card.check();
    expect(card.health).toEqual(authorizationHealth);
    expect(card.selection.has_authorization).toBe(true);
  });

  test.each(['disable', 'disconnect', 'dispose'] as const)('late renewal cannot undo %s', async (action): Promise<void> => {
    const { api, card } = setup();
    await card.loadHealth();
    const pending = deferred<RenewalResult>();
    vi.spyOn(api.authorization, 'renew').mockReturnValue(pending.promise);
    const get = vi.spyOn(api.connections, 'get');
    const renewing = card.renew();
    if (action === 'disable') await card.setEnabled();
    if (action === 'disconnect') { card.requestDisconnect(); await card.disconnect(); }
    if (action === 'dispose') card.dispose();
    pending.resolve({ status: 'refreshed', discovery_required: true });
    await renewing;
    expect(card.selection.enabled).toBe(false);
    expect(card.message).not.toContain('Authorization renewed');
    expect(get).not.toHaveBeenCalled();
  });

  test('late health is ignored after newer check, disable, and disposal', async (): Promise<void> => {
    const { api, card } = setup();
    const old = deferred<AuthorizationHealth>();
    vi.spyOn(api.authorization, 'getHealth').mockReturnValueOnce(old.promise);
    const loading = card.loadHealth();
    await card.refresh();
    await card.setEnabled();
    card.dispose();
    old.resolve(authorizationHealth);
    await loading;
    expect(card.health).toBeNull();
    expect(card.selection.has_authorization).toBe(false);
  });

  test('late renewal selection and health reads cannot repopulate after disable', async (): Promise<void> => {
    const { api, card } = setup();
    await card.loadHealth();
    const late = deferred<Selection>();
    const get = vi.spyOn(api.connections, 'get').mockReturnValueOnce(late.promise);
    const renewing = card.renew();
    await vi.waitFor(() => expect(get).toHaveBeenCalledOnce());
    await card.setEnabled();
    late.resolve(selection);
    await renewing;
    expect(card.selection.enabled).toBe(false);
    expect(card.message).not.toContain('Authorization renewed');
  });

  test.each(['disable', 'disconnect'] as const)('late manual check cannot undo %s', async (action): Promise<void> => {
    const { api, card } = setup();
    await card.loadHealth();
    const late = deferred<Selection>();
    vi.spyOn(api.connections, 'get').mockReturnValueOnce(late.promise);
    const refreshing = card.refresh();
    if (action === 'disable') await card.setEnabled();
    else { card.requestDisconnect(); await card.disconnect(); }
    late.resolve(selection);
    await refreshing;
    expect(card.selection.enabled).toBe(false);
    expect(card.message).not.toContain('Authorization status checked');
  });

  test('cancellation and a newer check reject older health responses', async (): Promise<void> => {
    const { api, card } = setup();
    const late = deferred<AuthorizationHealth>();
    vi.spyOn(api.authorization, 'getHealth').mockReturnValueOnce(late.promise);
    const loading = card.loadHealth();
    await card.start();
    await card.cancel();
    await card.refresh();
    late.resolve({ state: 'reconnect_required', reason: 'provider_rejected' });
    await loading;
    expect(card.health).toEqual(authorizationHealth);
    expect(card.attempt).toBeNull();
  });

  test('401 immediately clears owner data even if the parallel read is still pending', async (): Promise<void> => {
    const { api } = setup();
    const page = new ConnectionsState(api);
    await page.load();
    const card = page.cards[0];
    const pending = deferred<Selection>();
    vi.spyOn(api.connections, 'get').mockReturnValue(pending.promise);
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new AuthenticationRequiredError());
    const refreshing = card.refresh();
    await vi.waitFor(() => expect(page.phase).toBe('sign-in'));
    expect(page.cards).toEqual([]);
    expect(card.health).toBeNull();
    pending.resolve(selection);
    await refreshing;
    expect(page.cards).toEqual([]);
  });

  test('authentication loss wins over a concurrent failed details read', async (): Promise<void> => {
    const { api } = setup();
    const page = new ConnectionsState(api);
    await page.load();
    vi.spyOn(api.connections, 'get').mockRejectedValue(new HttpError(503, 'Unavailable', {}));
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new AuthenticationRequiredError());
    await page.cards[0].refresh();
    expect(page.phase).toBe('sign-in');
    expect(page.cards).toEqual([]);
  });

  test.each(['health', 'renew'] as const)('401 during %s clears every card and ignores another late result', async (operation): Promise<void> => {
    const { api } = setup();
    const page = new ConnectionsState(api);
    await page.load();
    const card = page.cards[0];
    await card.start();
    await card.cancel();
    if (operation === 'health') vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new AuthenticationRequiredError());
    else vi.spyOn(api.authorization, 'renew').mockRejectedValue(new AuthenticationRequiredError());
    if (operation === 'health') await card.refresh();
    else await card.renew();
    expect(page.phase).toBe('sign-in');
    expect(page.cards).toEqual([]);
    expect(card.health).toBeNull();
    expect(card.authorizationUrl).toBe('');
    expect(card.selection.display_name).toBe('');
  });
});
