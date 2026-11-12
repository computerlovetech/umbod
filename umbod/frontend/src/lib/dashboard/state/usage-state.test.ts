import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import type { UsagePort } from '../api';
import { personalUsageSchema, type PersonalUsage } from '../domain/usage-schemas';
import { deferred, usageSnapshot } from '../usage-fixtures.test-support';
import { UsageState } from './usage-state.svelte';

function setup(): { state: UsageState; get: ReturnType<typeof vi.fn<UsagePort['get']>>; lost: ReturnType<typeof vi.fn<() => void>> } {
  const get = vi.fn<UsagePort['get']>().mockResolvedValue(usageSnapshot());
  const lost = vi.fn<() => void>();
  return { state: new UsageState({ get }, lost), get, lost };
}

describe('personal usage state', () => {
  test('pending has no fabricated counts; zero snapshots retain all days', async (): Promise<void> => {
    const { state, get } = setup();
    const pending = deferred<PersonalUsage>();
    get.mockReturnValueOnce(pending.promise);
    const loading = state.refresh();
    expect(state.pending).toBe(true);
    expect(state.snapshot).toBeUndefined();
    expect(state.charts.activity.days).toEqual([]);
    expect(state.charts.mix.total).toBe(0);
    pending.resolve(usageSnapshot());
    await loading;
    expect(state.phase).toBe('ready');
    expect(state.charts.mix.total).toBe(0);
    expect(state.charts.activity.days).toHaveLength(7);
    expect(state.charts.mix.segments.map((segment) => segment.count)).toEqual([0, 0, 0]);
    expect(state.charts.outcomes.segments.map((segment) => segment.count)).toEqual([0, 0, 0]);
  });

  test('projects category and outcome totals without losing failures or cancellations', async (): Promise<void> => {
    const { state, get } = setup();
    const snapshot = usageSnapshot();
    const totals = {
      tool: { success: 14, failure: 1, cancelled: 2 },
      resource: { success: 3, failure: 4, cancelled: 5 },
      prompt: { success: 6, failure: 7, cancelled: 8 }
    };
    get.mockResolvedValue(personalUsageSchema.parse({
      ...snapshot, totals,
      daily: snapshot.daily.map((row, index) => index === 0 ? { ...row, counts: totals } : row)
    }));
    await state.refresh();
    expect(state.charts.mix.total).toBe(50);
    expect(state.charts.mix.segments.map((segment) => segment.count)).toEqual([17, 12, 21]);
    expect(state.charts.outcomes.segments.map((segment) => segment.count)).toEqual([14, 1, 2]);
    expect(state.charts.outcomes.successRate).toBe((14 / 17 * 100).toFixed(1));
    expect(state.charts.activity.days[0]).toMatchObject({ success: 14, failure: 1, cancelled: 2 });
  });

  test.each([503, 500])('failure %s clears snapshots and retry recovers', async (status): Promise<void> => {
    const { state, get } = setup();
    await state.refresh();
    get.mockRejectedValueOnce(new HttpError(status, 'private', { secret: 'private' }));
    await state.refresh();
    expect(state.phase).toBe(status === 503 ? 'unavailable' : 'error');
    expect(state.snapshot).toBeUndefined();
    expect(state.charts.activity.days).toEqual([]);
    expect(state.charts.mix.total).toBe(0);
    await state.refresh();
    expect(state.phase).toBe('ready');
  });

  test('period changes abort and fence late responses', async (): Promise<void> => {
    const { state, get } = setup();
    const old = deferred<PersonalUsage>();
    const current = deferred<PersonalUsage>();
    get.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const first = state.refresh();
    const signal = get.mock.calls[0][1];
    state.selectPeriod('30');
    expect(signal?.aborted).toBe(true);
    expect(state.days).toBe(30);
    expect(state.snapshot).toBeUndefined();
    current.resolve(usageSnapshot(30));
    await vi.waitFor(() => expect(state.phase).toBe('ready'));
    old.resolve(usageSnapshot(7, 'account-one', 10));
    await first;
    expect(state.charts.activity.days).toHaveLength(30);
    expect(state.charts.mix.total).toBe(0);
    state.selectPeriod('30');
    state.selectPeriod('14');
    expect(get).toHaveBeenCalledTimes(2);
  });

  test('catalogue identity change clears a snapshot and aborts previous identity reads', async (): Promise<void> => {
    const { state, get } = setup();
    await state.refresh();
    const old = deferred<PersonalUsage>();
    const next = deferred<PersonalUsage>();
    get.mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
    const first = state.refresh();
    const oldSignal = get.mock.calls[1][1];
    state.reconcileIdentity('account-two');
    expect(state.snapshot).toBeUndefined();
    expect(oldSignal?.aborted).toBe(true);
    next.resolve(usageSnapshot(7, 'account-two', 1));
    await vi.waitFor(() => expect(state.snapshot?.identity_key).toBe('account-two'));
    old.resolve(usageSnapshot());
    await first;
    expect(state.snapshot?.identity_key).toBe('account-two');
  });

  test('rejects a response from an unexpected identity or period', async (): Promise<void> => {
    const { state, get } = setup();
    state.reconcileIdentity('account-two');
    await state.refresh();
    expect(state.phase).toBe('error');
    expect(state.snapshot).toBeUndefined();
    get.mockResolvedValueOnce(usageSnapshot(30, 'account-two'));
    await state.refresh();
    expect(state.phase).toBe('error');
  });

  test('focus revalidation removes cached data before accepting a new authenticated identity', async (): Promise<void> => {
    const { state, get } = setup();
    await state.refresh();
    const next = deferred<PersonalUsage>();
    get.mockReturnValueOnce(next.promise);
    const focus = state.revalidate();
    expect(state.snapshot).toBeUndefined();
    expect(state.phase).toBe('loading');
    next.resolve(usageSnapshot(7, 'account-two'));
    await focus;
    expect(state.snapshot?.identity_key).toBe('account-two');
  });

  test.each([401, 403])('authentication loss %s clears snapshots and fences pending work', async (status): Promise<void> => {
    const { state, get, lost } = setup();
    await state.refresh();
    get.mockRejectedValueOnce(status === 401 ? new AuthenticationRequiredError() : new HttpError(403, 'private', null));
    await state.refresh();
    expect(state.snapshot).toBeUndefined();
    expect(state.phase).toBe(status === 401 ? 'sign-in' : 'forbidden');
    expect(lost).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
  });

  test.each(['authenticationLost', 'dispose'] as const)('%s aborts pending reads and prevents late restoration', async (operation): Promise<void> => {
    const { state, get } = setup();
    await state.refresh();
    const pending = deferred<PersonalUsage>();
    get.mockReturnValueOnce(pending.promise);
    const loading = state.refresh();
    const signal = get.mock.calls[1][1];
    state[operation]();
    expect(signal?.aborted).toBe(true);
    pending.resolve(usageSnapshot());
    await loading;
    expect(state.snapshot).toBeUndefined();
    if (operation === 'dispose') {
      await state.refresh();
      state.selectPeriod('30');
      state.reconcileIdentity('other');
      expect(get).toHaveBeenCalledTimes(2);
    }
  });
});
