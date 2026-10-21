import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { AuthorizationHealth } from '$lib/personal-connections/domain/schemas';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { ConnectionState } from '$lib/personal-connections/state/connection-state.svelte';
import { authorizationHealth, selection } from '$lib/personal-connections/test-fixtures';
import AppHeader from '$lib/components/header/AppHeader.svelte';
import ConnectionCard from './ConnectionCard.svelte';
import PersonalConnections from './PersonalConnections.svelte';

describe('personal connections presentation', () => {
  test('initial rendering is passive and briefly explains independent gates', () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const list = vi.spyOn(api.connections, 'list');
    const start = vi.spyOn(api.authorization, 'start');
    const body = render(PersonalConnections, { props: { createApi: (): PersonalConnectionsApi => api } }).body;
    expect(body).toContain('Loading connections');
    expect(body).toContain('independent requirements');
    expect(body).not.toContain('unknown attempt is never cancelled');
    expect(list).not.toHaveBeenCalled();
    expect(start).not.toHaveBeenCalled();
  });
  test('saved authorization is not falsely labelled connected or diagnosed expired', () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn());
    const body = render(ConnectionCard, { props: { state } }).body;
    for (const label of ['Authorization saved', 'Not available', 'Sign in again', 'Disable', 'Discover tools', 'Disconnect']) expect(body).toContain(label);
    expect(body).toContain('not a live provider health check');
    expect(body).not.toContain('Connected');
    expect(body).not.toContain('reconnect required');
  });
  test('pending sign-in presents only a safe user-clicked external link and manual controls', async () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn());
    await state.start();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain('target="_blank"');
    expect(body).toContain('rel="noopener noreferrer"');
    for (const label of ['Continue sign-in', 'Check sign-in status', 'Cancel sign-in']) expect(body).toContain(label);
    expect(body).not.toContain('<iframe');
    await state.cancel();
    const terminalBody = render(ConnectionCard, { props: { state } }).body;
    expect(terminalBody).not.toContain('provider.example');
    expect(terminalBody).not.toContain('Continue sign-in');
  });
  test('disconnect confirmation stays inline and separate from enablement', () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn());
    state.requestDisconnect();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain('Confirm disconnect');
    expect(body).toContain('Keep authorization');
    expect(body).toContain('Remove saved authorization and disable');
    expect(state.selection.enabled).toBe(true);
  });
  test.each<{ health: AuthorizationHealth; copy: string; renew: boolean }>([
    { health: { state: 'not_authorized' }, copy: 'Sign-in needed', renew: false },
    { health: authorizationHealth, copy: 'Authorization valid locally', renew: true },
    { health: { state: 'expired', expires_at: '2030-01-01T00:00:00Z', refresh_supported: true }, copy: 'Authorization expired', renew: true },
    { health: { state: 'unsupported' }, copy: 'Sign in again to replace unsupported authorization', renew: false },
    { health: { state: 'authorized', expires_at: '2030-01-01T00:00:00Z', refresh_supported: false }, copy: 'Authorization valid locally', renew: false },
    { health: { state: 'expired', expires_at: '2030-01-01T00:00:00Z', refresh_supported: false }, copy: 'Authorization expired', renew: false },
    { health: { state: 'reconnect_required', reason: 'provider_rejected' }, copy: 'The provider rejected this authorization.', renew: false },
    { health: { state: 'reconnect_required', reason: 'refresh_denied' }, copy: 'Authorization renewal was rejected.', renew: false },
    { health: { state: 'reconnect_required', reason: 'refresh_uncertain' }, copy: 'The renewal outcome could not be confirmed.', renew: false },
    { health: { state: 'refreshing', deadline: '2000-01-01T00:00:00Z' }, copy: 'Renewal in progress. Check status before another action.', renew: false }
  ])('presents $health.state independently of saved authorization and tools', async ({ health, copy, renew }): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: health });
    const state = new ConnectionState(selection, api, vi.fn<() => void>());
    await state.loadHealth();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain(copy);
    expect(body).toContain('Authorization saved');
    expect(body).toContain('Not available');
    expect(body.includes('Renew authorization')).toBe(renew);
    expect(body).toContain('Check authorization status');
    expect(body).toContain('Sign in again');
    if (health.state === 'authorized' || health.state === 'expired') {
      expect(body).toContain('Last checked:');
      expect(body).toContain('Based on saved records. The provider may still reject authorization or renewal.');
      expect(body).toContain('Expires:');
    }
  });
  test('unavailable health exposes safe manual recovery, never expiry or unsupported claims', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new HttpError(503, 'secret', { detail: 'secret' }));
    const state = new ConnectionState(selection, api, vi.fn<() => void>());
    await state.loadHealth();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain('Authorization status unavailable');
    expect(body).toContain('Check status');
    expect(body).not.toContain('Renew authorization');
    expect(body).not.toContain('Authorization expired');
    expect(body).not.toContain('unsupported authorization');
    expect(body).not.toContain('secret');
    expect(state.canDiscover).toBe(false);
  });
  test('header adds discoverable Connections without replacing account identity', () => {
    const body = render(AppHeader, { props: { accountIdentity: { kind: 'visible', name: 'Alex', email: null, picture: null, hiddenValues: { id: 'owner' } } } }).body;
    expect(body).toContain('href="/settings/connections"');
    expect(body).toContain('Connections');
    expect(body).toContain('Current account');
    expect(body).toContain('Alex');
  });
});
