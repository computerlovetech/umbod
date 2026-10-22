import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { AuthorizationHealth } from '$lib/personal-connections/domain/schemas';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { ConnectionState } from '$lib/personal-connections/state/connection-state.svelte';
import { authorizationHealth, completedAttempt, selection } from '$lib/personal-connections/test-fixtures';
import ConnectionCard from './ConnectionCard.svelte';

describe('personal connections presentation', () => {
  test('saved authorization is not falsely labelled connected or diagnosed expired', () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn());
    const body = render(ConnectionCard, { props: { state } }).body;
    for (const label of ['Authorization saved', 'Not available', 'Sign in again', 'Disable', 'Discover tools', 'Disconnect']) expect(body).toContain(label);
    expect(body).toContain('Personal access');
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
      expect(body).not.toContain('Based on saved records.');
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
    expect(body).toContain('Check authorization status');
    expect(body).not.toContain('Renew authorization');
    expect(body).not.toContain('Authorization expired');
    expect(body).not.toContain('unsupported authorization');
    expect(body).not.toContain('secret');
    expect(state.canDiscover).toBe(false);
  });
  test('catalogue notifications follow successful operations without replacing pending state', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const changed = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const state = new ConnectionState(selection, api, vi.fn(), changed);
    await state.loadHealth();
    await state.start();
    expect(changed).not.toHaveBeenCalled();
    const attempt = state.attempt;
    await state.refresh();
    expect(state.attempt).toEqual(attempt);
    expect(changed).toHaveBeenCalledTimes(1);
    vi.spyOn(api.authorization, 'get').mockResolvedValue(completedAttempt);
    await state.check();
    expect(changed).toHaveBeenCalledTimes(2);
    vi.spyOn(api.authorization, 'renew').mockResolvedValue({ status: 'refreshed', discovery_required: true });
    await state.renew();
    expect(changed).toHaveBeenCalledTimes(3);
    await state.discover();
    expect(changed).toHaveBeenCalledTimes(4);
    await state.setEnabled();
    expect(changed).toHaveBeenCalledTimes(5);
    state.requestDisconnect();
    await state.disconnect();
    expect(changed).toHaveBeenCalledTimes(6);
  });
  test('failed catalogue refresh cannot turn a successful mutation into an uncertain replay', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const changed = vi.fn<() => Promise<void>>().mockRejectedValue(new Error('private'));
    const state = new ConnectionState(selection, api, vi.fn(), changed);
    const enable = vi.spyOn(api.connections, 'setEnablement');
    await state.setEnabled();
    expect(enable).toHaveBeenCalledOnce();
    expect(state.selection.enabled).toBe(false);
    expect(state.message).toBe('Personal access disabled.');
    expect(state.needsRefresh).toBe(false);
    expect(state.error).toBe("Couldn't refresh connectors. Refresh the dashboard.");
    expect(state.error).not.toContain('private');
  });
  test('successful mutations retain their outcome when the following personal read fails', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const changed = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const state = new ConnectionState(selection, api, vi.fn(), changed);
    const enable = vi.spyOn(api.connections, 'setEnablement');
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new HttpError(503, 'private', {}));
    await state.setEnabled();
    await state.setEnabled();
    expect(enable).toHaveBeenCalledOnce();
    expect(changed).toHaveBeenCalledOnce();
    expect(state.selection.enabled).toBe(false);
    expect(state.message).toBe('Personal access disabled.');
    expect(state.needsRefresh).toBe(true);
    expect(state.error).toContain('Check authorization status');
    expect(state.error).not.toContain('private');
  });
  test('embedded controls omit duplicate identity and preserve pending attempts across renders', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn());
    await state.start();
    const attempt = state.attempt;
    const body = render(ConnectionCard, { props: { state, embedded: true } }).body;
    expect(body).not.toContain('<article');
    expect(body).not.toContain(selection.display_name);
    expect(body).not.toContain(selection.capability_description);
    expect(body).toContain('Personal access');
    expect(body).toContain('Continue sign-in');
    const reopened = render(ConnectionCard, { props: { state, embedded: true } }).body;
    expect(reopened).toContain('Check sign-in status');
    expect(state.attempt).toEqual(attempt);
  });
});
