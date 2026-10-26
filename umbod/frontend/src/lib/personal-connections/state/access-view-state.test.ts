import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '../api';
import type { AuthorizationHealth, Selection } from '../domain/schemas';
import { InMemoryPersonalConnectionsApi } from '../infrastructure/in-memory-api';
import type { PersonalAccessViewController } from '../presentation';
import { authorizationHealth, deferred, selection } from '../test-fixtures';
import { PersonalAccessViewState } from './access-view-state.svelte';
import { ConnectionState } from './connection-state.svelte';
import type { PersonalConnectionController } from './port';

interface Harness {
  readonly connection: PersonalConnectionController;
  readonly view: PersonalAccessViewController;
  readonly api: PersonalConnectionsApi;
}

function harness(health: AuthorizationHealth, overrides: Partial<Selection>): Harness {
  const current: Selection = { ...selection, runtime_available: true, runtime_unavailable_reason: '', ...overrides };
  const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([current], { calendar: health });
  const connection: PersonalConnectionController = new ConnectionState(current, api, vi.fn<() => void>());
  return { connection, api, view: new PersonalAccessViewState(() => connection) };
}

describe('personal access presentation contract', () => {
  test.each<{ health: AuthorizationHealth; overrides: Partial<Selection>; label: string; tone: string; primary: string }>([
    { health: authorizationHealth, overrides: {}, label: 'Ready to use', tone: 'success', primary: '' },
    { health: authorizationHealth, overrides: { enabled: false }, label: 'Disabled', tone: 'neutral', primary: 'Enable access' },
    { health: { state: 'not_authorized' }, overrides: { has_authorization: false }, label: 'Sign-in required', tone: 'warning', primary: 'Sign in' },
    { health: authorizationHealth, overrides: { runtime_available: false }, label: 'Tools not ready', tone: 'warning', primary: 'Refresh tools' },
    { health: { state: 'expired', expires_at: '2030-01-01T00:00:00Z', refresh_supported: true }, overrides: {}, label: 'Authorization expired', tone: 'warning', primary: 'Renew access' },
    { health: { state: 'expired', expires_at: '2030-01-01T00:00:00Z', refresh_supported: false }, overrides: {}, label: 'Authorization expired', tone: 'warning', primary: 'Sign in again' },
    { health: { state: 'unsupported' }, overrides: {}, label: 'Sign-in required', tone: 'warning', primary: 'Sign in again' },
    { health: { state: 'reconnect_required', reason: 'provider_rejected' }, overrides: {}, label: 'Sign-in required', tone: 'warning', primary: 'Sign in again' },
    { health: { state: 'reconnect_required', reason: 'refresh_denied' }, overrides: {}, label: 'Sign-in required', tone: 'warning', primary: 'Sign in again' },
    { health: { state: 'reconnect_required', reason: 'refresh_uncertain' }, overrides: {}, label: 'Sign-in required', tone: 'warning', primary: 'Sign in again' },
    { health: { state: 'refreshing', deadline: '2000-01-01T00:00:00Z' }, overrides: {}, label: 'Renewal in progress', tone: 'pending', primary: 'Check authorization status' },
    { health: authorizationHealth, overrides: { has_authorization: false }, label: 'Status needs checking', tone: 'warning', primary: 'Check authorization status' }
  ])('$label provides the appropriate single next step: $primary', async ({ health, overrides, label, tone, primary }): Promise<void> => {
    const { connection, view, api } = harness(health, overrides);
    const start = vi.spyOn(api.authorization, 'start');
    const discover = vi.spyOn(api.connections, 'discover');
    const renew = vi.spyOn(api.authorization, 'renew');
    await connection.loadHealth();
    expect(view.status.label).toBe(label);
    expect(view.status.tone).toBe(tone);
    expect(view.primaryLabel).toBe(primary);
    if (primary) expect(view.primaryDisabled).toBe(false);
    expect(start).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    expect(renew).not.toHaveBeenCalled();
  });

  test('loading or unavailable health never reports ready or diagnoses expiration', async (): Promise<void> => {
    const { connection, view, api } = harness(authorizationHealth, {});
    expect(view.status.label).toBe('Checking access…');
    expect(view.status.action).toBeNull();
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new HttpError(503, 'private', {}));
    await connection.loadHealth();
    expect(view.status.label).toBe('Status unavailable');
    expect(view.primaryLabel).toBe('Check authorization status');
    expect(view.status.description).not.toContain('expired');
    expect(view.menuActions.some((action) => action.id === 'renew')).toBe(false);
    expect(view.menuActions.find((action) => action.id === 'discover')?.disabled).toBe(true);
  });

  test('unconfirmed mutations require safe inspection instead of another recovery mutation', async (): Promise<void> => {
    const { connection, view, api } = harness(authorizationHealth, {});
    await connection.loadHealth();
    vi.spyOn(api.authorization, 'renew').mockRejectedValue(new HttpError(500, 'private', {}));
    const start = vi.spyOn(api.authorization, 'start');
    const discover = vi.spyOn(api.connections, 'discover');
    await connection.renew();
    expect(view.status.label).toBe('Status needs checking');
    expect(view.primaryLabel).toBe('Check authorization status');
    await view.perform('sign-in');
    await view.perform('discover');
    expect(start).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
    await view.perform('refresh');
    expect(connection.needsRefresh).toBe(false);
    expect(view.status.label).toBe('Ready to use');
  });

  test('starting sign-in never implicitly enables, renews, or discovers', async (): Promise<void> => {
    const { connection, view, api } = harness({ state: 'not_authorized' }, { has_authorization: false });
    const enable = vi.spyOn(api.connections, 'setEnablement');
    const renew = vi.spyOn(api.authorization, 'renew');
    const discover = vi.spyOn(api.connections, 'discover');
    const start = vi.spyOn(api.authorization, 'start');
    await connection.loadHealth();
    await view.perform('sign-in');
    expect(view.status.label).toBe('Sign-in needs attention');
    expect(view.status.tone).toBe('warning');
    expect(view.primaryLabel).toBe('Check sign-in status');
    expect(view.fallbackRequired).toBe(true);
    expect(view.menuActions.find((action) => action.id === 'cancel')?.disabled).toBe(false);
    await view.perform('sign-in');
    expect(start).toHaveBeenCalledOnce();
    expect(enable).not.toHaveBeenCalled();
    expect(renew).not.toHaveBeenCalled();
    expect(discover).not.toHaveBeenCalled();
  });

  test('progress blocks conflicting actions and exposes safe reasons', async (): Promise<void> => {
    const { connection, view, api } = harness(authorizationHealth, {});
    await connection.loadHealth();
    const pending = deferred<void>();
    vi.spyOn(api.connections, 'discover').mockReturnValue(pending.promise);
    const operation = connection.discover();
    expect(view.status.tone).toBe('pending');
    expect(view.status.action).toBeNull();
    expect(view.menuActions.find((action) => action.id === 'sign-in')?.disabled).toBe(true);
    expect(view.menuActions.find((action) => action.id === 'sign-in')?.reason).toBe('Another action is in progress.');
    pending.resolve(undefined);
    await operation;
    expect(view.status.label).toBe('Ready to use');
  });

  test('menu actions close the menu and disconnect remains a separate confirmation', async (): Promise<void> => {
    const { connection, view, api } = harness(authorizationHealth, {});
    await connection.loadHealth();
    const disconnect = vi.spyOn(api.connections, 'disconnect');
    view.setMenuOpen(true);
    await view.perform('disconnect');
    expect(view.menuOpen).toBe(false);
    expect(connection.confirmingDisconnect).toBe(true);
    expect(disconnect).not.toHaveBeenCalled();
    expect(connection.selection.enabled).toBe(true);
    connection.keepAuthorization();
    expect(connection.confirmingDisconnect).toBe(false);
  });

  test('disabled access offers enablement but never implicit sign-in', async (): Promise<void> => {
    const { connection, view, api } = harness({ state: 'not_authorized' }, { enabled: false, has_authorization: false });
    await connection.loadHealth();
    const start = vi.spyOn(api.authorization, 'start');
    expect(view.menuActions.some((action) => action.id === 'sign-in')).toBe(false);
    await view.perform('toggle');
    expect(connection.selection.enabled).toBe(true);
    expect(view.primaryLabel).toBe('Sign in');
    expect(start).not.toHaveBeenCalled();
  });
});
