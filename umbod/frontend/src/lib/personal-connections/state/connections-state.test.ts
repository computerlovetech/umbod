import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '../api';
import type { Attempt, Selection } from '../domain/schemas';
import { InMemoryPersonalConnectionsApi } from '../infrastructure/in-memory-api';
import { authorizationHealth, completedAttempt, deferred, pendingAttempt, selection } from '../test-fixtures';
import { ConnectionState } from './connection-state.svelte';
import { ConnectionsState } from './connections-state.svelte';

function setup(): { api: PersonalConnectionsApi; card: ConnectionState; authenticationLost: () => void } {
  const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
  const authenticationLost = vi.fn<() => void>();
  return { api, card: new ConnectionState(selection, api, authenticationLost), authenticationLost };
}

describe('personal connection public state behavior', () => {
  test('mount/load only reads selection and health; initiation remains explicit', async () => {
    const { api } = setup();
    const list = vi.spyOn(api.connections, 'list');
    const start = vi.spyOn(api.authorization, 'start');
    const discover = vi.spyOn(api.connections, 'discover');
    const page = new ConnectionsState(api);
    expect(page.phase).toBe('loading');
    await page.load();
    expect(list).toHaveBeenCalledOnce();
    expect(page.cards).toHaveLength(1);
    expect(start).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    page.dispose();
    expect(page.cards).toEqual([]);
  });
  test.each([403, 404])('represents unavailable %s separately from empty', async (status) => {
    const { api } = setup();
    vi.spyOn(api.connections, 'list').mockRejectedValue(new HttpError(status, 'private', { secret: 'private' }));
    const page = new ConnectionsState(api);
    await page.load();
    expect(page.phase).toBe('unavailable');
    expect(page.cards).toEqual([]);
  });
  test('empty listing is genuine ready state', async () => {
    const page = new ConnectionsState(new InMemoryPersonalConnectionsApi([]));
    await page.load();
    expect(page.phase).toBe('ready');
    expect(page.cards).toEqual([]);
  });
  test('401 clears all owner state, including another active attempt', async () => {
    const { api } = setup();
    const page = new ConnectionsState(api);
    await page.load();
    const card = page.cards[0];
    await card.start();
    vi.spyOn(api.connections, 'get').mockRejectedValue(new AuthenticationRequiredError());
    await card.refresh();
    expect(page.phase).toBe('sign-in');
    expect(page.cards).toEqual([]);
    expect(card.authorizationUrl).toBe('');
    expect(card.attempt).toBeNull();
    expect(card.selection.has_authorization).toBe(false);
  });
  test('stale list results cannot repopulate an unmounted page', async () => {
    const { api } = setup();
    const listing = deferred<{ connectors: Selection[] }>();
    vi.spyOn(api.connections, 'list').mockReturnValue(listing.promise);
    const page = new ConnectionsState(api);
    const loading = page.load();
    page.dispose();
    listing.resolve({ connectors: [selection] });
    await loading;
    expect(page.cards).toEqual([]);
  });
  test('starting sign-in never enables, discovers, polls or navigates; duplicate clicks are guarded', async () => {
    const { card, api } = setup();
    const start = vi.spyOn(api.authorization, 'start').mockResolvedValue(pendingAttempt);
    const get = vi.spyOn(api.authorization, 'get');
    const enable = vi.spyOn(api.connections, 'setEnablement');
    const discover = vi.spyOn(api.connections, 'discover');
    await Promise.all([card.start(), card.start()]);
    expect(start).toHaveBeenCalledOnce();
    expect(get).not.toHaveBeenCalled();
    expect(enable).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    expect(card.authorizationUrl).toBe(pendingAttempt.authorization_url);
    expect(card.attempt).not.toHaveProperty('authorization_url');
    expect(card.selection.has_authorization).toBe(true);
  });
  test('completed attempt clears URL and explicitly reloads selection without discovery', async () => {
    const { card, api } = setup();
    await card.start();
    vi.spyOn(api.authorization, 'get').mockResolvedValue(completedAttempt);
    const get = vi.spyOn(api.connections, 'get');
    const discover = vi.spyOn(api.connections, 'discover');
    await card.check();
    expect(get).toHaveBeenCalledOnce();
    expect(card.attempt).toBeNull();
    expect(card.authorizationUrl).toBe('');
    expect(card.message).toContain('Authorization saved');
    expect(discover).not.toHaveBeenCalled();
  });
  test.each(['failed', 'expired', 'cancelled'] as const)('terminal %s clears URL and preserves previous authorization', async (status) => {
    const { card, api } = setup();
    await card.start();
    vi.spyOn(api.authorization, 'get').mockResolvedValue({ ...completedAttempt, status });
    await card.check();
    expect(card.attempt).toBeNull();
    expect(card.authorizationUrl).toBe('');
    expect(card.selection.has_authorization).toBe(true);
  });
  test('known cancellation is explicit and preserves authorization', async () => {
    const { card, api } = setup();
    const cancel = vi.spyOn(api.authorization, 'cancel');
    await card.cancel();
    expect(cancel).not.toHaveBeenCalled();
    await card.start();
    await card.cancel();
    expect(cancel).toHaveBeenCalledOnce();
    expect(card.attempt).toBeNull();
    expect(card.selection.has_authorization).toBe(true);
  });
  test('disable suppresses a stale successful status and retains authorization', async () => {
    const { card, api } = setup();
    await card.start();
    const status = deferred<Attempt>();
    vi.spyOn(api.authorization, 'get').mockReturnValue(status.promise);
    const checking = card.check();
    await card.setEnabled();
    status.resolve(completedAttempt);
    await checking;
    expect(card.selection.enabled).toBe(false);
    expect(card.selection.has_authorization).toBe(true);
    expect(card.authorizationUrl).toBe('');
    expect(card.attempt).toBeNull();
  });
  test('disconnect needs confirmation and suppresses pending status without reenabling', async () => {
    const { card, api } = setup();
    const disconnect = vi.spyOn(api.connections, 'disconnect');
    const list = vi.spyOn(api.connections, 'list');
    await card.disconnect();
    expect(disconnect).not.toHaveBeenCalled();
    await card.start();
    const status = deferred<Attempt>();
    vi.spyOn(api.authorization, 'get').mockReturnValue(status.promise);
    const checking = card.check();
    card.requestDisconnect();
    await card.disconnect();
    status.resolve(completedAttempt);
    await checking;
    expect(list).toHaveBeenCalledOnce();
    expect(card.selection).toMatchObject({ enabled: false, has_authorization: false });
    expect(card.attempt).toBeNull();
  });
  test('a late completed selection GET cannot overwrite disablement', async () => {
    const { card, api } = setup();
    await card.start();
    vi.spyOn(api.authorization, 'get').mockResolvedValue(completedAttempt);
    const selectionRead = deferred<Selection>();
    const get = vi.spyOn(api.connections, 'get').mockReturnValue(selectionRead.promise);
    const checking = card.check();
    await vi.waitFor(() => expect(get).toHaveBeenCalledOnce());
    await card.setEnabled();
    selectionRead.resolve(selection);
    await checking;
    expect(card.selection.enabled).toBe(false);
  });
  test('discovery is explicit and reloads eligibility without enabling or authorizing', async () => {
    const { card, api } = setup();
    await card.loadHealth();
    const discover = vi.spyOn(api.connections, 'discover');
    const get = vi.spyOn(api.connections, 'get').mockResolvedValue({ ...selection, runtime_available: true, runtime_unavailable_reason: '' });
    const start = vi.spyOn(api.authorization, 'start');
    await card.discover();
    expect(discover).toHaveBeenCalledOnce();
    expect(get).toHaveBeenCalledOnce();
    expect(start).not.toHaveBeenCalled();
    expect(card.selection.runtime_available).toBe(true);
  });
  test('uncertain mutation never repeats; safe GET refresh unlocks later explicit actions', async () => {
    const { card, api } = setup();
    const start = vi.spyOn(api.authorization, 'start').mockRejectedValue(new NetworkError(new Error('https://secret?code=private')));
    const get = vi.spyOn(api.connections, 'get');
    await card.start();
    expect(card.error).toContain('outcome is unknown');
    expect(card.error).not.toMatch(/https|private/);
    await card.start();
    expect(start).toHaveBeenCalledOnce();
    await card.refresh();
    expect(get).toHaveBeenCalledOnce();
    expect(card.needsRefresh).toBe(false);
    expect(start).toHaveBeenCalledOnce();
  });
  test('conflicts never cancel or retry an unknown attempt; unsafe bodies stay private', async () => {
    const { card, api } = setup();
    vi.spyOn(api.authorization, 'start').mockRejectedValue(new HttpError(409, 'https://secret', { detail: 'code=private' }));
    const cancel = vi.spyOn(api.authorization, 'cancel');
    await card.start();
    expect(card.error).toContain('existing sign-in');
    expect(card.error).not.toMatch(/https|private/);
    expect(card.attempt).toBeNull();
    expect(cancel).not.toHaveBeenCalled();
  });
  test('disposing clears secrets and prevents late start responses', async () => {
    const { card, api } = setup();
    const started = deferred<typeof pendingAttempt>();
    vi.spyOn(api.authorization, 'start').mockReturnValue(started.promise);
    const starting = card.start();
    card.dispose();
    started.resolve(pendingAttempt);
    await starting;
    expect(card.attempt).toBeNull();
    expect(card.authorizationUrl).toBe('');
  });
});
