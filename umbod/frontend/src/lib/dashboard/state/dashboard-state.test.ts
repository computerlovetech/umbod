import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { authorizationHealth, selection } from '$lib/personal-connections/test-fixtures';
import type { DashboardApi } from '../api';
import type { UserCatalogue } from '../domain/schemas';
import { InMemoryDashboardApi } from '../infrastructure/in-memory-api';
import { catalogue, personalConnector, sharedConnector } from '../test-fixtures';
import type { DashboardController } from './port';
import { DashboardState } from './dashboard-state.svelte';

function setup(data: UserCatalogue = catalogue): { api: DashboardApi; personal: PersonalConnectionsApi; state: DashboardController } {
  const api: DashboardApi = new InMemoryDashboardApi(data);
  const personal: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
  return { api, personal, state: new DashboardState(api, personal) };
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => { resolve = complete; });
  return { promise, resolve };
}

describe('dashboard controller contract', () => {
  test('defaults to the first connector and ignores unknown selection IDs', async (): Promise<void> => {
    const { state } = setup();
    expect(state.selectedId).toBe('');
    expect(state.selectedConnector).toBeUndefined();
    await state.loadCatalogue();
    expect(state.selectedId).toBe('downstream_mcp:shared');
    expect(state.selectedConnector).toEqual(sharedConnector);
    state.selectConnector('missing');
    expect(state.selectedId).toBe('downstream_mcp:shared');
    expect(state.selectedConnector).toEqual(sharedConnector);
    state.selectConnector('');
    expect(state.selectedId).toBe('downstream_mcp:shared');
  });

  test('connector kinds distinguish colliding IDs without changing catalogue order', async (): Promise<void> => {
    const native = { ...sharedConnector, kind: 'native' as const };
    const { state } = setup({ ...catalogue, connectors: [sharedConnector, native] });
    await state.loadCatalogue();
    state.selectConnector('native:shared');
    expect(state.selectedId).toBe('native:shared');
    expect(state.selectedConnector).toEqual(native);
    expect(state.connectors).toEqual([sharedConnector, native]);
    state.selectConnector('downstream_mcp:shared');
    expect(state.selectedConnector).toEqual(sharedConnector);
  });

  test('selection is local and preserves personal authorization state across switches', async (): Promise<void> => {
    const { state, api, personal } = setup();
    await state.loadCatalogue();
    const card = state.personalCard('calendar')!;
    await card.start();
    const attempt = card.attempt;
    const catalogueRead = vi.spyOn(api.catalogue, 'list');
    const personalRead = vi.spyOn(personal.connections, 'list');
    const start = vi.spyOn(personal.authorization, 'start');
    const discover = vi.spyOn(personal.connections, 'discover');
    const enable = vi.spyOn(personal.connections, 'setEnablement');
    state.selectConnector('downstream_mcp:calendar');
    expect(state.selectedConnector).toEqual(personalConnector);
    state.selectConnector('downstream_mcp:shared');
    state.selectConnector('downstream_mcp:calendar');
    expect(state.personalCard('calendar')).toBe(card);
    expect(card.attempt).toBe(attempt);
    for (const operation of [catalogueRead, personalRead, start, discover, enable]) {
      expect(operation).not.toHaveBeenCalled();
    }
  });

  test('refresh retains selection through reorder and resolves the latest connector object', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    state.selectConnector('downstream_mcp:calendar');
    const previous = state.selectedConnector;
    const updated = { ...personalConnector, display_name: 'Updated calendar', capabilities: sharedConnector.capabilities };
    vi.spyOn(api.catalogue, 'list').mockResolvedValue({ ...catalogue, connectors: [updated, sharedConnector] });
    await state.loadCatalogue();
    expect(state.selectedId).toBe('downstream_mcp:calendar');
    expect(state.selectedConnector).toBe(state.connectors[0]);
    expect(state.selectedConnector).not.toBe(previous);
    expect(state.selectedConnector).toEqual(updated);
  });

  test('removal falls back to the first remaining connector and an empty catalogue clears selection', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    state.selectConnector('downstream_mcp:calendar');
    const list = vi.spyOn(api.catalogue, 'list').mockResolvedValue({ ...catalogue, connectors: [sharedConnector] });
    await state.loadCatalogue();
    expect(state.selectedId).toBe('downstream_mcp:shared');
    expect(state.selectedConnector).toEqual(sharedConnector);
    list.mockResolvedValue({ ...catalogue, connectors: [] });
    await state.loadCatalogue();
    expect(state.selectedId).toBe('');
    expect(state.selectedConnector).toBeUndefined();
  });

  test('identity change resets selection even when the previous connector remains available', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    state.selectConnector('downstream_mcp:calendar');
    vi.spyOn(api.catalogue, 'list').mockResolvedValue({ ...catalogue, identity_key: 'another-account' });
    await state.loadCatalogue();
    expect(state.selectedId).toBe('downstream_mcp:shared');
    expect(state.selectedConnector).toEqual(sharedConnector);
  });

  test.each(['authenticationLost', 'dispose'] as const)('%s clears a loaded selection', async (operation): Promise<void> => {
    const { state } = setup();
    await state.loadCatalogue();
    state.selectConnector('downstream_mcp:calendar');
    state[operation]();
    expect(state.selectedId).toBe('');
    expect(state.selectedConnector).toBeUndefined();
  });

  test('transient catalogue failure preserves the selected connector', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    state.selectConnector('downstream_mcp:calendar');
    const selected = state.selectedConnector;
    vi.spyOn(api.catalogue, 'list').mockRejectedValue(new HttpError(503, 'private', {}));
    await state.loadCatalogue();
    expect(state.selectedId).toBe('downstream_mcp:calendar');
    expect(state.selectedConnector).toBe(selected);
  });
  test('reads the permitted catalogue without requesting administrative data or mutating personal access', async (): Promise<void> => {
    const { personal, state } = setup();
    const start = vi.spyOn(personal.authorization, 'start');
    const discover = vi.spyOn(personal.connections, 'discover');
    const enable = vi.spyOn(personal.connections, 'setEnablement');
    await state.loadCatalogue();
    expect(state.phase).toBe('ready');
    expect(state.connectors.map((connector) => connector.connector_id)).toEqual(['shared', 'calendar']);
    expect(state.personalPhase).toBe('ready');
    expect(start).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    expect(enable).not.toHaveBeenCalled();
  });

  test('disabled personal support does not request personal APIs', async (): Promise<void> => {
    const { state, personal } = setup({ ...catalogue, personal_enabled: false, connectors: [sharedConnector] });
    const list = vi.spyOn(personal.connections, 'list');
    await state.loadCatalogue();
    expect(state.phase).toBe('ready');
    expect(state.connectors).toEqual([sharedConnector]);
    expect(list).not.toHaveBeenCalled();
  });

  test('pending sign-in survives catalogue refresh without restarting or replacing its state', async (): Promise<void> => {
    const { state, personal } = setup();
    await state.loadCatalogue();
    const card = state.personalCard('calendar')!;
    await card.start();
    const attemptId = card.attempt?.attempt_id;
    const start = vi.spyOn(personal.authorization, 'start');
    await state.loadCatalogue();
    expect(state.personalCard('calendar')).toBe(card);
    expect(card.attempt?.attempt_id).toBe(attemptId);
    expect(start).not.toHaveBeenCalled();
  });

  test('changed identity disposes previous personal authorization attempts', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    const oldCard = state.personalCard('calendar')!;
    await oldCard.start();
    vi.spyOn(api.catalogue, 'list').mockResolvedValue({ ...catalogue, identity_key: 'another-account' });
    await state.loadCatalogue();
    expect(state.personalCard('calendar')).not.toBe(oldCard);
    expect(state.personalCard('calendar')?.attempt).toBeNull();
    expect(oldCard.attempt).toBeNull();
    expect(oldCard.authorizationUrl).toBe('');
  });

  test('returning to the dashboard revalidates identity without restarting sign-in', async (): Promise<void> => {
    const { state, api, personal } = setup();
    const list = vi.spyOn(api.catalogue, 'list');
    await state.refreshOnFocus();
    expect(list).not.toHaveBeenCalled();
    await state.loadCatalogue();
    const card = state.personalCard('calendar')!;
    await card.start();
    const start = vi.spyOn(personal.authorization, 'start');
    await state.refreshOnFocus();
    expect(list).toHaveBeenCalledTimes(2);
    expect(state.personalCard('calendar')).toBe(card);
    expect(card.attempt).not.toBeNull();
    expect(start).not.toHaveBeenCalled();
  });

  test('revocation removes the entry and its pending personal state', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    const oldCard = state.personalCard('calendar')!;
    await oldCard.start();
    vi.spyOn(api.catalogue, 'list').mockResolvedValue({ ...catalogue, connectors: [sharedConnector] });
    await state.loadCatalogue();
    expect(state.personalCard('calendar')).toBeUndefined();
    expect(oldCard.attempt).toBeNull();
    expect(state.connectors).toEqual([sharedConnector]);
  });

  test('background refresh retains visible entries and reconciles externally changed personal selection', async (): Promise<void> => {
    const { state, api, personal } = setup();
    await state.loadCatalogue();
    const card = state.personalCard('calendar')!;
    await card.start();
    const pending = deferred<UserCatalogue>();
    vi.spyOn(api.catalogue, 'list').mockReturnValueOnce(pending.promise);
    vi.spyOn(personal.connections, 'list').mockResolvedValue({ connectors: [{ ...selection, enabled: false, has_authorization: false }] });
    const loading = state.loadCatalogue();
    expect(state.phase).toBe('ready');
    expect(state.refreshing).toBe(true);
    expect(state.connectors).toEqual(catalogue.connectors);
    pending.resolve(catalogue);
    await loading;
    expect(state.personalCard('calendar')).toBe(card);
    expect(card.selection.enabled).toBe(false);
    expect(card.selection.has_authorization).toBe(false);
    expect(card.attempt).toBeNull();
    expect(state.refreshing).toBe(false);
  });

  test.each([403, 404])('personal unavailability %s clears previously loaded controls', async (status): Promise<void> => {
    const { state, personal } = setup();
    await state.loadCatalogue();
    const card = state.personalCard('calendar')!;
    await card.start();
    vi.spyOn(personal.connections, 'list').mockRejectedValue(new HttpError(status, 'private', {}));
    await state.loadCatalogue();
    expect(state.phase).toBe('ready');
    expect(state.personalPhase).toBe('unavailable');
    expect(state.personalCards).toEqual([]);
    expect(card.attempt).toBeNull();
  });

  test('personal read failure leaves shared catalogue usable', async (): Promise<void> => {
    const { state, personal } = setup();
    vi.spyOn(personal.connections, 'list').mockRejectedValue(new HttpError(503, 'private', {}));
    await state.loadCatalogue();
    expect(state.phase).toBe('ready');
    expect(state.connectors).toEqual(catalogue.connectors);
    expect(state.personalPhase).toBe('error');
  });

  test.each(['catalogue', 'personal'] as const)('%s authentication loss clears all protected data', async (source): Promise<void> => {
    const { state, personal, api } = setup();
    await state.loadCatalogue();
    if (source === 'catalogue') vi.spyOn(api.catalogue, 'list').mockRejectedValue(new AuthenticationRequiredError());
    else vi.spyOn(personal.connections, 'list').mockRejectedValue(new AuthenticationRequiredError());
    await state.loadCatalogue();
    expect(state.phase).toBe('sign-in');
    expect(state.selectedId).toBe('');
    expect(state.selectedConnector).toBeUndefined();
    expect(state.connectors).toEqual([]);
    expect(state.personalCards).toEqual([]);
  });

  test('successful personal mutation refreshes capabilities without reconstructing personal state', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    const card = state.personalCard('calendar')!;
    vi.spyOn(api.catalogue, 'list').mockResolvedValue({
      ...catalogue,
      connectors: catalogue.connectors.map((connector) => ({ ...connector, capabilities: sharedConnector.capabilities }))
    });
    await card.discover();
    expect(state.personalCard('calendar')).toBe(card);
    expect(state.connectors[1].capabilities).toEqual(sharedConnector.capabilities);
  });

  test('late catalogue reads cannot restore data after disposal', async (): Promise<void> => {
    const { state, api } = setup();
    const pending = deferred<UserCatalogue>();
    vi.spyOn(api.catalogue, 'list').mockReturnValue(pending.promise);
    const loading = state.loadCatalogue();
    state.dispose();
    pending.resolve(catalogue);
    await loading;
    expect(state.connectors).toEqual([]);
    expect(state.personalCards).toEqual([]);
  });

  test('older catalogue responses cannot replace a newer catalogue', async (): Promise<void> => {
    const { state, api } = setup();
    const pending = deferred<UserCatalogue>();
    vi.spyOn(api.catalogue, 'list').mockReturnValueOnce(pending.promise).mockResolvedValue({ ...catalogue, connectors: [] });
    const first = state.loadCatalogue();
    await state.loadCatalogue();
    pending.resolve(catalogue);
    await first;
    expect(state.connectors).toEqual([]);
  });

  test('forbidden catalogue refresh removes protected entries', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    vi.spyOn(api.catalogue, 'list').mockRejectedValue(new HttpError(403, 'private', { secret: 'private' }));
    await state.loadCatalogue();
    expect(state.phase).toBe('forbidden');
    expect(state.selectedId).toBe('');
    expect(state.selectedConnector).toBeUndefined();
    expect(state.connectors).toEqual([]);
    expect(state.personalCards).toEqual([]);
  });

  test('initial catalogue failure reports a safe error rather than an empty result', async (): Promise<void> => {
    const { state, api } = setup();
    vi.spyOn(api.catalogue, 'list').mockRejectedValue(new HttpError(503, 'private', { secret: 'private' }));
    await state.loadCatalogue();
    expect(state.phase).toBe('error');
    expect(state.connectors).toEqual([]);
  });

  test('secondary refresh failure preserves valid entries and personal operation outcomes', async (): Promise<void> => {
    const { state, api } = setup();
    await state.loadCatalogue();
    const card = state.personalCard('calendar')!;
    vi.spyOn(api.catalogue, 'list').mockRejectedValue(new HttpError(503, 'private', { secret: 'private' }));
    await card.setEnabled();
    expect(state.phase).toBe('ready');
    expect(state.connectors).toEqual(catalogue.connectors);
    expect(state.personalCard('calendar')).toBe(card);
    expect(card.message).toBe('Personal access disabled.');
    expect(card.needsRefresh).toBe(false);
    expect(state.catalogueError).toBe("Couldn't refresh connectors");
  });
});
