import { InMemoryAttemptScheduler } from '$lib/personal-connections/infrastructure/in-memory-attempt-scheduler';
import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { AuthorizationHealth } from '$lib/personal-connections/domain/schemas';
import type { PersonalConnectionsApi } from '$lib/personal-connections/api';
import type { AuthorizationBrowser } from '$lib/personal-connections/authorization-browser';
import { InMemoryAuthorizationBrowser } from '$lib/personal-connections/infrastructure/in-memory-authorization-browser';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { ConnectionState } from '$lib/personal-connections/state/connection-state.svelte';
import type { PersonalConnectionController } from '$lib/personal-connections/state/port';
import { PersonalAccessViewState } from '$lib/personal-connections/state/access-view-state.svelte';
import type { PersonalAccessViewController } from '$lib/personal-connections/presentation';
import { authorizationHealth, completedAttempt, selection } from '$lib/personal-connections/test-fixtures';
import ConnectionCard from './ConnectionCard.svelte';

describe('personal connections presentation', () => {
  test('saved authorization is not falsely labelled connected or diagnosed expired', () => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn(), undefined, undefined, new InMemoryAttemptScheduler());
    const body = render(ConnectionCard, { props: { state } }).body;
    for (const label of ['Authorization saved', 'Not available', 'Checking access…', 'Personal access actions for Calendar']) expect(body).toContain(label);
    expect(body).not.toContain('Ready to use');
    expect(body).not.toContain('role="menuitem"');
    expect(body).toContain('Personal access');
    expect(body).not.toContain('Connected');
    expect(body).not.toContain('reconnect required');
  });
  test('blocked automatic opening retains a safe sign-in fallback without exposing secondary actions', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn(), undefined, undefined, new InMemoryAttemptScheduler());
    await state.start();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).not.toContain('<a ');
    expect(body).not.toContain('primary-action');
    expect(body).not.toContain('next-step');
    for (const label of ['actions menu', 'could not be opened automatically']) expect(body).toContain(label);
    const view: PersonalAccessViewController = new PersonalAccessViewState(() => state);
    expect(view.menuActions.find((action) => action.id === 'cancel')?.disabled).toBe(false);
    expect(view.menuActions.find((action) => action.id === 'continue-sign-in')?.disabled).toBe(false);
    expect(body).not.toMatch(/<button[^>]*>Continue sign-in/);
    expect(body).not.toContain('Cancel sign-in');
    expect(body).not.toContain('<iframe');
    await state.cancel();
    const terminalBody = render(ConnectionCard, { props: { state } }).body;
    expect(terminalBody).not.toContain('provider.example');
    expect(terminalBody).not.toContain('Continue sign-in');
  });
  test('automatically opened sign-in needs no additional continue-link step', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const browser: AuthorizationBrowser = new InMemoryAuthorizationBrowser();
    const state: PersonalConnectionController = new ConnectionState(selection, api, vi.fn<() => void>(), async (): Promise<void> => {}, browser, new InMemoryAttemptScheduler());
    await state.start();
    expect(state.authorizationOpened).toBe(true);
    const body = render(ConnectionCard, { props: { state, embedded: true } }).body;
    expect(body).toContain('Complete sign-in in the window or tab that opened');
    expect(body).toContain('It will close automatically');
    expect(body).not.toContain('Check sign-in status');
    expect(body).toContain('Waiting for sign-in');
    expect(body).not.toContain('Continue sign-in');
    expect(body).not.toContain('could not be opened automatically');
    expect(body).not.toContain('Open sign-in page again');
    expect(body).not.toContain('<a ');
  });
  test('disconnect confirmation stays inline and separate from enablement', (): void => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const state = new ConnectionState(selection, api, vi.fn(), undefined, undefined, new InMemoryAttemptScheduler());
    state.requestDisconnect();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain('Confirm disconnect');
    expect(body).toContain('Keep authorization');
    expect(body).toContain('Remove saved authorization and disable');
    expect(state.selection.enabled).toBe(true);
  });
  test.each<{ health: AuthorizationHealth; copy: string; renew: boolean }>([
    { health: { state: 'not_authorized' }, copy: 'Sign-in required', renew: false },
    { health: authorizationHealth, copy: 'Authorization valid locally', renew: true },
    { health: { state: 'expired', expires_at: '2030-01-01T00:00:00Z', refresh_supported: true }, copy: 'Authorization expired', renew: true },
    { health: { state: 'unsupported' }, copy: 'Your saved authorization is no longer supported', renew: false },
    { health: { state: 'authorized', expires_at: '2030-01-01T00:00:00Z', refresh_supported: false }, copy: 'Authorization valid locally', renew: false },
    { health: { state: 'expired', expires_at: '2030-01-01T00:00:00Z', refresh_supported: false }, copy: 'Authorization expired', renew: false },
    { health: { state: 'reconnect_required', reason: 'provider_rejected' }, copy: 'The provider rejected this authorization.', renew: false },
    { health: { state: 'reconnect_required', reason: 'refresh_denied' }, copy: 'Authorization renewal was rejected.', renew: false },
    { health: { state: 'reconnect_required', reason: 'refresh_uncertain' }, copy: 'The renewal outcome could not be confirmed.', renew: false },
    { health: { state: 'refreshing', deadline: '2000-01-01T00:00:00Z' }, copy: 'Renewal is already in progress. Check status before another action.', renew: false }
  ])('presents $health.state independently of saved authorization and tools', async ({ health, copy, renew }): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: health });
    const state = new ConnectionState(selection, api, vi.fn<() => void>(), undefined, undefined, new InMemoryAttemptScheduler());
    await state.loadHealth();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain(copy);
    expect(body).toContain('Authorization saved');
    expect(body).toContain('Not available');
    const view: PersonalAccessViewController = new PersonalAccessViewState(() => state);
    expect(view.menuActions.some((action) => action.id === 'renew')).toBe(renew);
    expect(view.menuActions.some((action) => action.id === 'refresh')).toBe(true);
    expect(view.menuActions.some((action) => action.label === 'Sign in again')).toBe(true);
    expect(body).not.toContain('role="menuitem"');
    if (health.state === 'authorized' || health.state === 'expired') {
      expect(body).toContain('Last checked');
      expect(body).not.toContain('Based on saved records.');
      expect(body).toContain('Expires');
    }
  });
  test('unavailable health exposes safe manual recovery, never expiry or unsupported claims', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new HttpError(503, 'secret', { detail: 'secret' }));
    const state = new ConnectionState(selection, api, vi.fn<() => void>(), undefined, undefined, new InMemoryAttemptScheduler());
    await state.loadHealth();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain('Status unavailable');
    expect(body).toContain('Check status to try again');
    expect(body).not.toContain('Renew authorization');
    expect(body).not.toContain('Authorization expired');
    expect(body).not.toContain('unsupported authorization');
    expect(body).not.toContain('secret');
    expect(state.canDiscover).toBe(false);
  });
  test('a failed quiet health refresh preserves Ready and reports separate status feedback', async (): Promise<void> => {
    const current = { ...selection, runtime_available: true };
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([current], { calendar: authorizationHealth });
    const state = new ConnectionState(current, api, vi.fn<() => void>(), undefined, undefined, new InMemoryAttemptScheduler());
    await state.loadHealth();
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValue(new HttpError(503, 'secret', {}));
    await state.loadHealth();
    const body = render(ConnectionCard, { props: { state } }).body;
    expect(body).toContain('Ready to use');
    expect(body).toContain(`role="status">${state.healthRefreshError}`);
    expect(state.healthRefreshError).not.toBe('');
    expect(body).not.toContain('Status unavailable');
    expect(body).not.toMatch(/<button[^>]*>Sign in/);
    expect(body).not.toContain('<a ');
    state.dispose();
  });
  test('catalogue notifications follow successful operations without replacing pending state', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const changed = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const state = new ConnectionState(selection, api, vi.fn(), changed, undefined, new InMemoryAttemptScheduler());
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
    const state = new ConnectionState(selection, api, vi.fn(), changed, undefined, new InMemoryAttemptScheduler());
    const enable = vi.spyOn(api.connections, 'setEnablement');
    await state.setEnabled();
    expect(enable).toHaveBeenCalledOnce();
    expect(state.selection.enabled).toBe(false);
    expect(state.message).toBe('Personal access disabled.');
    expect(state.needsRefresh).toBe(true);
    expect(state.error).toBe("Couldn't refresh connectors. Check authorization status to refresh the dashboard.");
    expect(state.error).not.toContain('private');
  });
  test('successful mutations retain their outcome when the following personal read fails', async (): Promise<void> => {
    const api: PersonalConnectionsApi = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const changed = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const state = new ConnectionState(selection, api, vi.fn(), changed, undefined, new InMemoryAttemptScheduler());
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
    const state = new ConnectionState(selection, api, vi.fn(), undefined, undefined, new InMemoryAttemptScheduler());
    await state.start();
    const attempt = state.attempt;
    const body = render(ConnectionCard, { props: { state, embedded: true } }).body;
    expect(body).not.toContain('<article');
    expect(body).not.toContain(selection.display_name);
    expect(body).not.toContain(selection.capability_description);
    expect(body).toContain('Personal access');
    expect(body).toContain('actions menu');
    expect(body).not.toContain('<a ');
    const reopened = render(ConnectionCard, { props: { state, embedded: true } }).body;
    expect(reopened).not.toContain('Check sign-in status');
    expect(state.attempt).toEqual(attempt);
  });
});
