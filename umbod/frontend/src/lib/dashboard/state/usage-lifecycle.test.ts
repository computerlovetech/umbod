import { describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import { InMemoryDashboardApi } from '../infrastructure/in-memory-api';
import { catalogue } from '../test-fixtures';
import { deferred, usageSnapshot } from '../usage-fixtures.test-support';
import type { PersonalUsage } from '../domain/usage-schemas';
import { UsagePageState } from './usage-page-state.svelte';

function identity(id: string): HeaderAccountIdentityState {
  return { kind: 'visible', name: id, email: null, picture: null, hiddenValues: { id } };
}

function setup(): { api: InMemoryDashboardApi; state: UsagePageState } {
  const api = new InMemoryDashboardApi({ ...catalogue, personal_enabled: false });
  vi.spyOn(api.usage, 'get').mockResolvedValue(usageSnapshot());
  return { api, state: new UsagePageState(api.usage) };
}

describe('Dashboard usage identity lifecycle', () => {
  test('header identifiers are not compared with opaque usage ownership keys', async (): Promise<void> => {
    const { api, state } = setup();
    state.observeAccountIdentity(identity('header-one'));
    await state.usage.refresh();
    state.observeAccountIdentity(identity('header-one'));
    expect(state.usage.snapshot?.identity_key).toBe('account-one');
    expect(api.usage.get).toHaveBeenCalledTimes(1);
    state.dispose();
  });

  test('account changes clear usage and hidden identity fences pending work', async (): Promise<void> => {
    const { api, state } = setup();
    state.observeAccountIdentity(identity('one'));
    await state.usage.refresh();
    const pending = deferred<PersonalUsage>();
    vi.mocked(api.usage.get).mockReturnValueOnce(pending.promise);
    state.observeAccountIdentity(identity('two'));
    expect(state.usage.snapshot).toBeUndefined();
    state.observeAccountIdentity({ kind: 'hidden' });
    pending.resolve(usageSnapshot(7, 'account-two'));
    await Promise.resolve();
    expect(state.usage.snapshot).toBeUndefined();
    expect(state.usage.phase).toBe('sign-in');
    state.dispose();
  });

  test.each([401, 403])('usage access loss %s clears loaded data', async (status): Promise<void> => {
    const { api, state } = setup();
    await state.usage.refresh();
    vi.mocked(api.usage.get).mockRejectedValue(new HttpError(status, 'private', null));
    await state.usage.refresh();
    expect(state.usage.snapshot).toBeUndefined();
    expect(state.usage.phase).toBe(status === 401 ? 'sign-in' : 'forbidden');
    state.dispose();
  });

  test('focus clears usage and disposal fences a pending refresh', async (): Promise<void> => {
    const { api, state } = setup();
    await state.usage.refresh();
    const usageRead = deferred<PersonalUsage>();
    vi.mocked(api.usage.get).mockReturnValueOnce(usageRead.promise);
    const loading = state.refreshOnFocus();
    expect(state.usage.snapshot).toBeUndefined();
    expect(state.usage.pending).toBe(true);
    state.dispose();
    usageRead.resolve(usageSnapshot());
    await loading;
    expect(state.usage.snapshot).toBeUndefined();
  });
});
