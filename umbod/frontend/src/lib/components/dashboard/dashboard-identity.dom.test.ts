import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { mountWorkspace } from '#lib/components/workspace/mount-workspace.test-support.js';
import { tick, unmount } from 'svelte';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
import { activityOverview, dashboardActivityApi } from '#lib/insights/activity/activity.test-support.js';
import type { ActivityOverview, ActivitySessionPage } from '#lib/insights/activity/domain/activity-schemas.js';
import { DashboardActivityState } from '#lib/dashboard/state/dashboard-activity-state.svelte.js';
import { WorkspaceAccessState } from '#lib/workspace/workspace-access-state.svelte.js';
import { WorkspaceScope } from '#lib/workspace/workspace-scope.svelte.js';
import type { WorkspaceProfile } from '#lib/workspace/domain/profile.js';
import { DashboardIdentityProps } from './identity-props.test-support.svelte';
import Dashboard from './Dashboard.svelte';

let component: ReturnType<typeof mountWorkspace> | undefined;

beforeEach((): void => {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
});

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function identity(id: string): HeaderAccountIdentityState {
  return { kind: 'visible', name: `Account ${id}`, email: null, picture: null, hiddenValues: { id: `header-${id}` } };
}

function profile(id: string): WorkspaceProfile {
  return { identity_key: `verified-${id}`, user: { id: `header-${id}`, name: `Account ${id}`, email: null, picture: null }, capabilities: { administration: true } };
}

function chart(): Element | null { return document.querySelector('[aria-label="Tool activity"]'); }

function button(label: string): HTMLButtonElement {
  const match = [...document.querySelectorAll('button')].find((item): boolean => item.textContent?.trim() === label);
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}

describe('Dashboard account isolation', () => {
  test('leaving Dashboard while hidden does not suspend account details for other pages', async (): Promise<void> => {
    const access = new WorkspaceAccessState({ profile: { get: async (): Promise<WorkspaceProfile> => profile('A') } });
    await access.load();
    const workspace = new WorkspaceScope(access);
    const dashboard = new DashboardActivityState(dashboardActivityApi('verified-A', 1), workspace);
    dashboard.start(true);
    dashboard.observeVisibility(false);
    dashboard.dispose();

    expect(workspace.personalIdentity).toMatchObject({ kind: 'visible', hiddenValues: { id: 'verified-A' } });
    workspace.dispose();
  });

  test.each(['B', 'hidden'] as const)('clears activity and aborts both reads when the account changes to %s', async (destination): Promise<void> => {
    const inputs = new DashboardIdentityProps(identity('A'));
    const profileB = Promise.withResolvers<WorkspaceProfile>();
    const pendingOverview = Promise.withResolvers<ActivityOverview>();
    const pendingSessions = Promise.withResolvers<ActivitySessionPage>();
    const api = dashboardActivityApi('verified-A', 9);
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockResolvedValueOnce(profile('A')).mockReturnValue(profileB.promise);
    component = mountWorkspace(Dashboard, { target: document.body, props: {
      get accountIdentity(): HeaderAccountIdentityState { return inputs.identity; },
      createApi: () => api,
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    } }, '/dashboard');
    await vi.waitFor(() => expect(chart()?.textContent).toContain('63 calls'));
    api.overview.mockReturnValueOnce(pendingOverview.promise);
    api.sessions.mockReturnValueOnce(pendingSessions.promise);
    const harness = document.querySelector<HTMLInputElement>('input[value="harness"]');
    expect(harness).not.toBeNull();
    harness!.click();
    await tick();
    button('Refresh activity').click();
    const overviewSignal = api.overview.mock.lastCall?.[1];
    const sessionsSignal = api.sessions.mock.lastCall?.[1];
    inputs.replace(destination === 'B' ? identity('B') : { kind: 'hidden' });
    await tick();
    expect(overviewSignal?.aborted).toBe(true);
    expect(sessionsSignal?.aborted).toBe(true);
    expect(chart()).toBeNull();
    expect(document.querySelector('[aria-label="Activity source"]')).toBeNull();
    const previous = activityOverview('verified-A', 7, 9);
    pendingOverview.resolve(previous);
    pendingSessions.resolve({ identity_key: 'verified-A', period: previous.period, sessions: [], page: { kind: 'end' } });
    await tick();
    expect(chart()).toBeNull();
    expect(api.overview).toHaveBeenCalledTimes(2);
    if (destination === 'hidden') {
      expect(getProfile).toHaveBeenCalledTimes(1);
      return;
    }
    expect(getProfile).toHaveBeenCalledTimes(2);
    const next = activityOverview('verified-B', 7, 1);
    api.overview.mockResolvedValue(next);
    api.sessions.mockResolvedValue({ identity_key: 'verified-B', period: next.period, sessions: [], page: { kind: 'end' } });
    profileB.resolve(profile('B'));
    await vi.waitFor(() => expect(chart()?.textContent).toContain('7 calls'));
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B');
  });

  test('waits for verification and never renders a response for the fallback account', async (): Promise<void> => {
    const verified = Promise.withResolvers<WorkspaceProfile>();
    const api = dashboardActivityApi('verified-B', 1);
    api.overview.mockResolvedValueOnce(activityOverview('header-A', 7, 9));
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockReturnValue(verified.promise);
    component = mountWorkspace(Dashboard, { target: document.body, props: {
      accountIdentity: identity('A'), createApi: () => api,
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    } }, '/dashboard');
    await vi.waitFor(() => expect(getProfile).toHaveBeenCalledTimes(1));
    expect(api.overview).not.toHaveBeenCalled();
    expect(api.sessions).not.toHaveBeenCalled();
    verified.resolve(profile('B'));
    await vi.waitFor(() => expect(document.body.textContent).toContain('Could not load the activity summary.'));
    expect(chart()).toBeNull();
    button('Refresh activity').click();
    await vi.waitFor(() => expect(chart()?.textContent).toContain('7 calls'));
  });

  test.each([
    { status: 'sign-in', error: new AuthenticationRequiredError(), message: 'Sign in to view your activity.' },
    { status: 'forbidden', error: new HttpError(403, 'Forbidden', null), message: 'Access to activity is unavailable.' }
  ])('clears visible activity on $status from a session read', async ({ error, message }): Promise<void> => {
    const api = dashboardActivityApi('verified-A', 1);
    component = mountWorkspace(Dashboard, { target: document.body, props: {
      accountIdentity: identity('A'), createApi: () => api,
      createWorkspaceApi: () => ({ profile: { get: async (): Promise<WorkspaceProfile> => profile('A') } })
    } }, '/dashboard');
    await vi.waitFor(() => expect(chart()?.textContent).toContain('7 calls'));
    document.querySelector<HTMLInputElement>('input[value="harness"]')?.click();
    await tick();
    document.querySelector<HTMLInputElement>('input[value="mcp"]')?.click();
    api.sessions.mockRejectedValueOnce(error);
    button('30 days').click();
    const read = api.overview.mock.lastCall?.[1];
    await vi.waitFor(() => expect(chart()?.textContent).toContain('30 calls'));
    const harness = document.querySelector<HTMLInputElement>('input[value="harness"]');
    expect(harness).not.toBeNull();
    harness!.click();
    await vi.waitFor(() => expect(document.body.textContent).toContain(message));
    expect(read?.aborted).toBe(true);
    expect(chart()).toBeNull();
    expect(document.querySelector('[aria-label="Activity source"]')).toBeNull();
  });

  test.each(['focus', 'visibility'] as const)('reverifies on %s and retains source and period for the same account', async (event): Promise<void> => {
    const verified = Promise.withResolvers<WorkspaceProfile>();
    const pending = Promise.withResolvers<ActivityOverview>();
    const api = dashboardActivityApi('verified-A', 1);
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockResolvedValueOnce(profile('A')).mockReturnValue(verified.promise);
    component = mountWorkspace(Dashboard, { target: document.body, props: {
      accountIdentity: identity('A'), createApi: () => api,
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    } }, '/dashboard');
    await vi.waitFor(() => expect(chart()?.textContent).toContain('7 calls'));
    const harness = document.querySelector<HTMLInputElement>('input[value="harness"]');
    expect(harness).not.toBeNull();
    harness!.click();
    api.overview.mockReturnValueOnce(pending.promise);
    button('30 days').click();
    const pendingSignal = api.overview.mock.lastCall?.[1];
    if (event === 'focus') window.dispatchEvent(new Event('focus'));
    else {
      vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
      document.dispatchEvent(new Event('visibilitychange'));
      await tick();
      expect(getProfile).toHaveBeenCalledTimes(1);
      expect(document.querySelector('[aria-label="Activity source"]')).toBeNull();
      vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
      document.dispatchEvent(new Event('visibilitychange'));
    }
    await vi.waitFor(() => expect(getProfile).toHaveBeenCalledTimes(2));
    expect(pendingSignal?.aborted).toBe(true);
    expect(document.querySelector('[aria-label="Activity source"]')).toBeNull();
    expect(api.overview).toHaveBeenCalledTimes(2);
    pending.resolve(activityOverview('verified-A', 30, 9));
    verified.resolve(profile('A'));
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('input[value="harness"]')?.checked).toBe(true));
    expect(api.overview).toHaveBeenCalledTimes(3);
    expect(api.overview).toHaveBeenLastCalledWith(30, expect.any(AbortSignal));
    expect(button('30 days').getAttribute('aria-pressed')).toBe('true');
    expect(chart()).toBeNull();
  });
});
