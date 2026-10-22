import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '../api';
import type { Attempt, Selection } from '../domain/schemas';
import { InMemoryPersonalConnectionsApi } from '../infrastructure/in-memory-api';
import { authorizationHealth, completedAttempt, deferred, pendingAttempt, selection } from '../test-fixtures';
import { ConnectionState } from './connection-state.svelte';
import { createPersonalDashboard } from './dashboard-test-helper';

function setup(): { api: PersonalConnectionsApi; card: ConnectionState; authenticationLost: () => void } {
  const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
  const authenticationLost = vi.fn<() => void>();
  return { api, card: new ConnectionState(selection, api, authenticationLost), authenticationLost };
}

describe('personal connection public state behavior', () => {
  test.each(['disable', 'disconnect'] as const)('reconciles external %s without retaining a stale attempt', async (action): Promise<void> => {
    const { api, card } = setup();
    await card.start();
    if (action === 'disable') await api.connections.setEnablement('calendar', { enabled: false });
    else await api.connections.disconnect('calendar');
    const updated = await api.connections.get('calendar');
    await card.reconcileSelection(updated);
    expect(card.selection).toEqual(updated);
    expect(card.selection.enabled).toBe(false);
    expect(card.selection.has_authorization).toBe(action === 'disable');
    expect(card.attempt).toBeNull();
    expect(card.authorizationUrl).toBe('');
    expect(card.healthPhase).toBe('ready');
    if (action === 'disconnect') expect(card.health).toEqual({ state: 'not_authorized' });
  });
  test('enabled external selections preserve pending sign-in and uncertain outcome recovery', async (): Promise<void> => {
    const { api, card } = setup();
    await card.start();
    const attempt = card.attempt;
    const url = card.authorizationUrl;
    vi.spyOn(api.authorization, 'get').mockRejectedValueOnce(new NetworkError('private'));
    await card.check();
    const error = card.error;
    await card.reconcileSelection({ ...selection, runtime_available: true });
    expect(card.selection.runtime_available).toBe(true);
    expect(card.attempt).toEqual(attempt);
    expect(card.authorizationUrl).toBe(url);
    expect(card.needsRefresh).toBe(true);
    expect(card.error).toBe(error);
    expect(card.health).toEqual(authorizationHealth);
  });
  test('external health failure remains local and preserves valid pending sign-in', async (): Promise<void> => {
    const { api, card } = setup();
    await card.start();
    const attempt = card.attempt;
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new HttpError(503, 'private', {}));
    await card.reconcileSelection({ ...selection, display_name: 'Updated server' });
    expect(card.selection.display_name).toBe('Updated server');
    expect(card.attempt).toEqual(attempt);
    expect(card.healthPhase).toBe('unavailable');
    expect(card.needsRefresh).toBe(false);
    expect(card.error).not.toContain('private');
  });
  test.each(['busy', 'checking', 'disposed'] as const)('ignores external selections while %s', async (phase): Promise<void> => {
    const { api, card } = setup();
    const pending = deferred<Attempt>();
    const starting = deferred<typeof pendingAttempt>();
    let operation: Promise<void> = Promise.resolve();
    if (phase === 'busy') {
      vi.spyOn(api.authorization, 'start').mockReturnValue(starting.promise);
      operation = card.start();
    } else if (phase === 'checking') {
      await card.start();
      vi.spyOn(api.authorization, 'get').mockReturnValue(pending.promise);
      operation = card.check();
    } else card.dispose();
    const previous = card.selection;
    const health = vi.spyOn(api.authorization, 'getHealth');
    await card.reconcileSelection({ ...selection, enabled: false });
    expect(card.selection).toEqual(previous);
    expect(health).not.toHaveBeenCalled();
    if (phase === 'checking') pending.resolve(completedAttempt);
    if (phase === 'busy') starting.resolve(pendingAttempt);
    await operation;
    card.dispose();
  });
  test('mount/load only reads selection and health; initiation remains explicit', async () => {
    const { api } = setup();
    const list = vi.spyOn(api.connections, 'list');
    const start = vi.spyOn(api.authorization, 'start');
    const discover = vi.spyOn(api.connections, 'discover');
    const page = createPersonalDashboard(api);
    expect(page.phase).toBe('loading');
    await page.loadCatalogue();
    expect(list).toHaveBeenCalledOnce();
    expect(page.personalCards).toHaveLength(1);
    expect(start).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    page.dispose();
    expect(page.personalCards).toEqual([]);
  });
  test.each([403, 404])('represents unavailable %s separately from empty', async (status) => {
    const { api } = setup();
    vi.spyOn(api.connections, 'list').mockRejectedValue(new HttpError(status, 'private', { secret: 'private' }));
    const page = createPersonalDashboard(api);
    await page.loadCatalogue();
    expect(page.personalPhase).toBe('unavailable');
    expect(page.personalCards).toEqual([]);
  });
  test('empty listing is genuine ready state', async () => {
    const page = createPersonalDashboard(new InMemoryPersonalConnectionsApi([]));
    await page.loadCatalogue();
    expect(page.phase).toBe('ready');
    expect(page.personalCards).toEqual([]);
  });
  test('401 clears all owner state, including another active attempt', async () => {
    const { api } = setup();
    const page = createPersonalDashboard(api);
    await page.loadCatalogue();
    const card = page.personalCards[0];
    await card.start();
    vi.spyOn(api.connections, 'get').mockRejectedValue(new AuthenticationRequiredError());
    await card.refresh();
    expect(page.phase).toBe('sign-in');
    expect(page.personalCards).toEqual([]);
    expect(card.authorizationUrl).toBe('');
    expect(card.attempt).toBeNull();
    expect(card.selection.has_authorization).toBe(false);
  });
  test('stale list results cannot repopulate an unmounted page', async () => {
    const { api } = setup();
    const listing = deferred<{ connectors: Selection[] }>();
    vi.spyOn(api.connections, 'list').mockReturnValue(listing.promise);
    const page = createPersonalDashboard(api);
    const loading = page.loadCatalogue();
    page.dispose();
    listing.resolve({ connectors: [selection] });
    await loading;
    expect(page.personalCards).toEqual([]);
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
    expect(card.message).toBe('Discovery completed.');
    expect(card.message).not.toContain('Approval and permissions remain independent');
  });
  test('known discovery failure is specific, sanitized and locked until manual reconciliation', async (): Promise<void> => {
    const { card, api, authenticationLost } = setup();
    await card.loadHealth();
    const discover = vi.spyOn(api.connections, 'discover').mockRejectedValue(new HttpError(409, 'https://private.test?secret=token', {
      detail: { code: 'personal_tool_discovery_unavailable' }
    }));
    const get = vi.spyOn(api.connections, 'get');
    const health = vi.spyOn(api.authorization, 'getHealth');
    const start = vi.spyOn(api.authorization, 'start');
    const cancel = vi.spyOn(api.authorization, 'cancel');
    const renew = vi.spyOn(api.authorization, 'renew');
    const enable = vi.spyOn(api.connections, 'setEnablement');
    await card.discover();
    expect(card.error).toBe('Tool discovery could not be completed. Check authorization status before trying again.');
    expect(card.error).not.toMatch(/sign-in|conflict|private|https|secret|token/);
    expect(card.needsRefresh).toBe(true);
    expect(card.canDiscover).toBe(false);
    expect(card.canRenew).toBe(false);
    expect(card.selection).toEqual(selection);
    expect(card.health).toEqual(authorizationHealth);
    expect(authenticationLost).not.toHaveBeenCalled();
    await card.discover();
    await card.start();
    await card.renew();
    await card.setEnabled();
    expect(discover).toHaveBeenCalledOnce();
    for (const call of [get, health, start, cancel, renew, enable]) expect(call).not.toHaveBeenCalled();
    get.mockRejectedValueOnce(new NetworkError('private'));
    await card.refresh();
    expect(card.needsRefresh).toBe(true);
    await card.discover();
    expect(discover).toHaveBeenCalledOnce();
    await card.refresh();
    expect(card.needsRefresh).toBe(false);
    expect(discover).toHaveBeenCalledOnce();
    await card.discover();
    expect(discover).toHaveBeenCalledTimes(2);
  });
  test.each([
    null,
    {},
    { detail: null },
    { detail: 'personal_tool_discovery_unavailable' },
    { detail: { code: 409 } },
    { detail: { code: 'unknown_private_code' } },
    { detail: { code: 'personal_tool_discovery_unavailable', message: 'private' } },
    { detail: { code: 'personal_tool_discovery_unavailable' }, secret: 'private' }
  ])('unrecognized discovery conflicts keep safe fallback guidance %#', async (body): Promise<void> => {
    const { card, api } = setup();
    await card.loadHealth();
    const discover = vi.spyOn(api.connections, 'discover').mockRejectedValue(new HttpError(409, 'private secret', body));
    await card.discover();
    expect(card.error).toContain('Another operation is in progress.');
    expect(card.error).not.toMatch(/private|secret|personal_tool/);
    expect(card.needsRefresh).toBe(true);
    await card.discover();
    expect(discover).toHaveBeenCalledOnce();
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
    expect(card.error).toContain('Check the known sign-in attempt');
    expect(card.error).not.toMatch(/https|private/);
    expect(card.attempt).toBeNull();
    expect(cancel).not.toHaveBeenCalled();
  });
  test.each([
    { code: 'personal_oauth_provider_unsupported', copy: 'Could not start sign-in. An administrator must check this MCP server’s OAuth compatibility.' },
    { code: 'personal_oauth_invalid_request', copy: 'Sign-in request rejected.' }
  ])('explains $code safely without unlocking or replaying sign-in', async ({ code, copy }): Promise<void> => {
    const { card, api, authenticationLost } = setup();
    await card.loadHealth();
    const start = vi.spyOn(api.authorization, 'start').mockRejectedValue(new HttpError(422, 'https://private.test?secret=token', {
      detail: { code, message: 'password=private', authorization_url: 'https://private.test', client_secret: 'private' }
    }));
    const get = vi.spyOn(api.connections, 'get');
    const health = vi.spyOn(api.authorization, 'getHealth');
    const cancel = vi.spyOn(api.authorization, 'cancel');
    const discover = vi.spyOn(api.connections, 'discover');
    const renew = vi.spyOn(api.authorization, 'renew');
    const enable = vi.spyOn(api.connections, 'setEnablement');
    await card.start();
    expect(card.error).toBe(`${copy} Check authorization status before another action.`);
    expect(card.error).not.toMatch(/private|https|password|token|secret/);
    expect(card.needsRefresh).toBe(true);
    expect(card.canRenew).toBe(false);
    expect(card.canDiscover).toBe(false);
    expect(card.attempt).toBeNull();
    expect(card.authorizationUrl).toBe('');
    expect(card.selection).toEqual(selection);
    expect(card.health).toEqual(authorizationHealth);
    expect(authenticationLost).not.toHaveBeenCalled();
    await card.start();
    await card.renew();
    await card.discover();
    await card.setEnabled();
    expect(start).toHaveBeenCalledOnce();
    for (const call of [get, health, cancel, discover, renew, enable]) expect(call).not.toHaveBeenCalled();
    get.mockRejectedValueOnce(new NetworkError('private'));
    await card.refresh();
    expect(card.needsRefresh).toBe(true);
    await card.start();
    expect(start).toHaveBeenCalledOnce();
    await card.refresh();
    expect(card.needsRefresh).toBe(false);
    expect(start).toHaveBeenCalledOnce();
    await card.start();
    expect(start).toHaveBeenCalledTimes(2);
  });
  test.each([
    { status: 422, body: null },
    { status: 422, body: {} },
    { status: 422, body: { detail: null } },
    { status: 422, body: { detail: 'personal_oauth_provider_unsupported' } },
    { status: 422, body: { detail: { code: 422 } } },
    { status: 422, body: { detail: { code: ['personal_oauth_invalid_request'] } } },
    { status: 422, body: { detail: { code: 'unknown_private_code' } } },
    { status: 400, body: { detail: { code: 'personal_oauth_invalid_request' } } },
    { status: 500, body: { detail: { code: 'personal_oauth_provider_unsupported' } } }
  ])('keeps generic safe guidance for unrecognized initiation errors %#', async ({ status, body }): Promise<void> => {
    const { card, api } = setup();
    vi.spyOn(api.authorization, 'start').mockRejectedValue(new HttpError(status, 'private secret', body));
    await card.start();
    expect(card.error).toBe('Operation failed. Check authorization status before another action.');
    expect(card.needsRefresh).toBe(true);
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
