import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '../api';
import type { AuthorizationHealth } from '../domain/schemas';
import { InMemoryPersonalConnectionsApi } from '../infrastructure/in-memory-api';
import { authorizationHealth, deferred, selection } from '../test-fixtures';
import { PersonalAccessViewState } from './access-view-state.svelte';
import { createPersonalDashboard } from './dashboard-test-helper';

function readyApi(): PersonalConnectionsApi {
  return new InMemoryPersonalConnectionsApi([{ ...selection, runtime_available: true, runtime_unavailable_reason: '' }], { calendar: authorizationHealth });
}

describe('quiet access revalidation', () => {
  test('only the initial health read shows checking and concurrent reads are coalesced', async (): Promise<void> => {
    const api = readyApi();
    const initial = deferred<AuthorizationHealth>();
    const read = vi.spyOn(api.authorization, 'getHealth').mockReturnValue(initial.promise);
    const page = createPersonalDashboard(api);
    const loading = page.loadCatalogue();
    await vi.waitFor(() => expect(page.personalCards).toHaveLength(1));
    const card = page.personalCards[0];
    const view = new PersonalAccessViewState(() => card);
    expect(view.status.label).toBe('Checking access…');
    const concurrent = card.loadHealth();
    expect(read).toHaveBeenCalledOnce();
    initial.resolve(authorizationHealth);
    await Promise.all([loading, concurrent]);
    expect(view.status.label).toBe('Ready to use');
    page.dispose();
  });

  test('focus refresh retains ready status, the existing card and its timestamp while health is pending', async (): Promise<void> => {
    const api = readyApi();
    const page = createPersonalDashboard(api);
    await page.loadCatalogue();
    const card = page.personalCards[0];
    const view = new PersonalAccessViewState(() => card);
    const checkedAt = card.healthCheckedAt;
    const refreshed = deferred<AuthorizationHealth>();
    const read = vi.spyOn(api.authorization, 'getHealth').mockReturnValue(refreshed.promise);
    const refreshing = page.refreshOnFocus();
    await vi.waitFor(() => expect(read).toHaveBeenCalledOnce());
    await page.refreshOnFocus();
    expect(read).toHaveBeenCalledOnce();
    expect(page.personalCards[0]).toBe(card);
    expect(card.healthPhase).toBe('ready');
    expect(card.healthCheckedAt).toBe(checkedAt);
    expect(view.status.label).toBe('Ready to use');
    refreshed.resolve({ state: 'expired', expires_at: '2020-01-01T00:00:00Z', refresh_supported: false });
    await refreshing;
    expect(view.status.label).toBe('Authorization expired');
    page.dispose();
  });

  test('failed background checks retain last confirmed facts with a separate retry notice', async (): Promise<void> => {
    const api = readyApi();
    const page = createPersonalDashboard(api);
    await page.loadCatalogue();
    const card = page.personalCards[0];
    const view = new PersonalAccessViewState(() => card);
    const checkedAt = card.healthCheckedAt;
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValueOnce(new HttpError(503, 'secret', { detail: 'secret' }));
    await page.refreshOnFocus();
    expect(view.status.label).toBe('Ready to use');
    expect(card.health).toEqual(authorizationHealth);
    expect(card.healthPhase).toBe('ready');
    expect(card.healthCheckedAt).toBe(checkedAt);
    expect(card.healthRefreshError).toContain('Showing the last confirmed status');
    expect(card.healthRefreshError).not.toContain('secret');
    expect(view.menuActions.find((action) => action.id === 'refresh')?.disabled).toBe(false);
    await view.perform('refresh');
    expect(card.healthRefreshError).toBe('');
    expect(view.status.label).toBe('Ready to use');
    page.dispose();
  });

  test('authentication loss during a quiet refresh clears protected state rather than preserving ready', async (): Promise<void> => {
    const api = readyApi();
    const page = createPersonalDashboard(api);
    await page.loadCatalogue();
    const card = page.personalCards[0];
    vi.spyOn(api.authorization, 'getHealth').mockRejectedValueOnce(new AuthenticationRequiredError());
    await page.refreshOnFocus();
    expect(page.phase).toBe('sign-in');
    expect(page.personalCards).toEqual([]);
    expect(card.health).toBeNull();
    expect(card.healthRefreshError).toBe('');
    expect(card.selection.has_authorization).toBe(false);
  });
});
