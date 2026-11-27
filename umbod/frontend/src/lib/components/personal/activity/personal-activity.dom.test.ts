import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import { ActivityState } from '#lib/insights/activity/activity-state.svelte.js';
import type { ActivityApi } from '#lib/insights/activity/domain/activity-api.js';
import type { ActivityOverview, ActivitySessionPage, ActivitySessionReport, ActivitySessionSummary } from '#lib/insights/activity/domain/activity-schemas.js';
import PersonalActivity from './PersonalActivity.svelte';

const identity = 'verified-account';
const period: ActivityOverview['period'] = {
  days: 7, as_of: '2026-03-07T08:00:00Z',
  window: { start: '2026-03-01T00:00:00Z', end: '2026-03-08T00:00:00Z' }
};
const outcomes = { success: 3, failure: 1, unknown: 2 };
const session: ActivitySessionSummary = {
  key: { source: 'codex', session_id: 'first/path' },
  first_seen_at: '2026-03-07T06:00:00Z', last_seen_at: '2026-03-07T07:00:00Z', outcomes
};
const older: ActivitySessionSummary = { ...session, key: { source: 'claude-code', session_id: 'older' } };
const third: ActivitySessionSummary = { ...older, key: { source: 'codex_exec', session_id: 'third' } };
const report: ActivitySessionReport = {
  identity_key: identity, session, top_tools: [{ tool_name: 'Read', count: 3 }],
  failed_tools: [{ tool_name: 'Edit', count: 1 }], has_more_failed_tools: false, skill_activations: 4
};
const zero = { success: 0, failure: 0, cancelled: 0 };
const counts = { tool: zero, resource: zero, prompt: zero };
const overview: ActivityOverview = {
  identity_key: identity, period,
  harness: { status: 'available', summary: { outcomes, top_tools: [{ tool_name: 'Overview tool', count: 12 }], skill_activations: 9 } },
  mcp: { status: 'available', summary: {
    as_of: period.as_of, range: { start: '2026-03-01', end: '2026-03-08', timezone: 'UTC' },
    totals: counts, top_tools: [], daily: Array.from({ length: 7 }, (_, index) => ({ date: `2026-03-0${index + 1}`, counts }))
  } }
};

function activityApi(): { [K in keyof ActivityApi]: ReturnType<typeof vi.fn<ActivityApi[K]>> } {
  return {
    overview: vi.fn<ActivityApi['overview']>().mockResolvedValue(overview),
    sessions: vi.fn<ActivityApi['sessions']>().mockImplementation(async (query) => ({
      identity_key: identity, period,
      sessions: query.cursor ? [older, third] : query.q === 'no match' ? [] : [session, older],
      page: query.cursor || query.q === 'no match' ? { kind: 'end' } : { kind: 'more', cursor: 'next-page' }
    })),
    session: vi.fn<ActivityApi['session']>().mockResolvedValue(report)
  };
}

let mounted: ReturnType<typeof mount> | undefined;
let state: ActivityState | undefined;

afterEach(async (): Promise<void> => {
  state?.dispose();
  if (mounted) await unmount(mounted);
  document.body.replaceChildren();
});

function mountActivity(api: ActivityApi): ActivityState {
  const activity = new ActivityState(api, identity, () => identity);
  state = activity;
  mounted = mount(PersonalActivity, { target: document.body, props: { state: activity } });
  return activity;
}

async function render(api: ActivityApi, source: 'harness' | 'mcp' = 'harness'): Promise<ActivityState> {
  const activity = mountActivity(api);
  await activity.refresh();
  flushSync();
  if (source === 'harness') {
    chooseSource('harness');
    await vi.waitFor(() => expect(activity.sessions.kind).not.toBe('loading'));
  }
  return activity;
}

function button(label: string): HTMLButtonElement {
  const match = [...document.querySelectorAll('button')].find((item): boolean => item.textContent?.trim() === label);
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}

function text(): string { return document.body.textContent ?? ''; }

function searchDetails(): HTMLDetailsElement {
  const details = document.querySelector('details');
  if (!details) throw new Error('Session search disclosure not found');
  return details;
}

function submitSearch(query: string): void {
  const input = document.querySelector<HTMLInputElement>('input[type="search"][aria-label="Search sessions"]');
  if (!input?.form) throw new Error('Session search form not found');
  input.value = query;
  input.form.dispatchEvent(new SubmitEvent('submit', { cancelable: true, bubbles: true }));
}

function sessionCards(): NodeListOf<HTMLButtonElement> {
  return document.querySelectorAll<HTMLButtonElement>('ul[aria-label="Harness sessions, newest first"] button');
}

function sourceControl(source: 'harness' | 'mcp'): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>(`input[type="radio"][value="${source}"]`);
  if (!input) throw new Error(`Activity source not found: ${source}`);
  return input;
}

function chooseSource(source: 'harness' | 'mcp'): void {
  sourceControl(source).click();
  flushSync();
}

describe('personal activity dashboard', (): void => {
  it('defaults to MCP even when Harness has activity, and loads sessions only after switching', async (): Promise<void> => {
    const api = activityApi();
    await render(api, 'mcp');
    expect(sourceControl('mcp').checked).toBe(true);
    expect(api.sessions).not.toHaveBeenCalled();
    button('30 days').click();
    await vi.waitFor(() => expect(text()).toContain('Cancelled'));
    expect(sourceControl('mcp').checked).toBe(true);
    expect(api.sessions).not.toHaveBeenCalled();
    chooseSource('harness');
    await vi.waitFor(() => expect(sessionCards()).toHaveLength(2));
    expect(api.sessions).toHaveBeenCalledWith({ days: 30, q: '', cursor: undefined }, expect.any(AbortSignal));
  });

  it('renders distinct outcomes and applies one period selector to both sources', async (): Promise<void> => {
    const api = activityApi();
    await render(api);
    expect(text()).toContain('Unknown');
    expect(text()).not.toContain('Cancelled');
    expect(document.querySelector('svg[role="img"]')?.getAttribute('aria-label')).toContain('2 unknown');
    chooseSource('mcp');
    expect(text()).toContain('Cancelled');
    expect(text()).not.toContain('Unknown');
    expect(document.querySelector('details')).toBeNull();
    button('30 days').click();
    expect(api.overview).toHaveBeenLastCalledWith(30, expect.any(AbortSignal));
    expect(api.sessions).toHaveBeenCalledTimes(1);
    chooseSource('harness');
    expect(api.sessions).toHaveBeenLastCalledWith({ days: 30, q: '', cursor: undefined }, expect.any(AbortSignal));
  });

  it('paginates and searches keyboard-navigable session cards without interrupting a pending report', async (): Promise<void> => {
    const api = activityApi();
    const pending = Promise.withResolvers<ActivitySessionReport>();
    api.session.mockReturnValueOnce(pending.promise);
    await render(api);
    const details = searchDetails();
    const summary = details.querySelector('summary');
    const metrics = document.querySelector('[aria-label="Tool call outcomes"]');
    if (!summary || !metrics) throw new Error('Session search or Harness metrics not found');
    expect(summary.textContent).toBe('Search session');
    expect(details.open).toBe(false);
    summary.click();
    expect(details.open).toBe(true);
    expect(details.compareDocumentPosition(metrics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const cards = sessionCards();
    expect(cards).toHaveLength(2);
    expect(cards[0].textContent).toContain('first/path');
    cards[0].focus();
    cards[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(document.activeElement).toBe(cards[1]);
    cards[0].click();
    flushSync();
    expect(api.session).toHaveBeenCalledWith(session.key, expect.any(AbortSignal));
    expect(cards[0].getAttribute('aria-pressed')).toBe('true');
    button('Load more sessions').click();
    await vi.waitFor(() => expect(text()).toContain('third'));
    expect(api.sessions).toHaveBeenLastCalledWith({ days: 7, q: '', cursor: 'next-page' }, expect.any(AbortSignal));
    expect(sessionCards()).toHaveLength(3);
    submitSearch('no match');
    await vi.waitFor(() => expect(text()).toContain('No matching sessions.'));
    expect(api.sessions).toHaveBeenLastCalledWith({ days: 7, q: 'no match', cursor: undefined }, expect.any(AbortSignal));
    expect(document.querySelector('[aria-label="Session statistics"]')).not.toBeNull();
    expect(api.session.mock.lastCall?.[1]?.aborted).toBe(false);
    pending.resolve(report);
    await vi.waitFor(() => expect(text()).toContain('Failed tools'));
    expect(text()).not.toContain('Session detail');
    expect(text()).not.toContain('First observed activity');
    expect(text()).not.toContain('Last observed activity');
    expect(text()).toContain('Skill activations');
    expect(document.querySelector('[aria-label="Tools by failed call count"]')?.textContent).toContain('Edit');
    expect(api.session).toHaveBeenCalledTimes(1);
  });

  it('replaces the overview even while session detail is pending or failed, and refreshes only the selected detail', async (): Promise<void> => {
    const api = activityApi();
    const pending = Promise.withResolvers<ActivitySessionReport>();
    api.session.mockReturnValueOnce(pending.promise);
    await render(api);
    expect(text()).toContain('Overview tool');
    sessionCards()[0].click();
    flushSync();
    expect(document.querySelector('section[aria-label="Session statistics"]')?.getAttribute('aria-busy')).toBe('true');
    expect(document.querySelector('[aria-label="Time period"]')).toBeNull();
    expect(text()).not.toContain('Overview tool');
    expect(sourceControl('harness').checked).toBe(true);
    expect(button('Back to overview')).toBeDefined();

    pending.reject(new HttpError(500, 'Unexpected error', null));
    await vi.waitFor(() => expect(text()).toContain('Could not load session detail.'));
    expect(document.querySelector('[aria-label="Time period"]')).toBeNull();
    expect(text()).not.toContain('Overview tool');
    button('Refresh session').click();
    await vi.waitFor(() => expect(text()).toContain('Failed tools'));
    expect(api.session).toHaveBeenCalledTimes(2);
    expect(api.session).toHaveBeenLastCalledWith(session.key, expect.any(AbortSignal));
    expect(api.overview).toHaveBeenCalledTimes(1);
    expect(api.sessions).toHaveBeenCalledTimes(1);
    expect(sessionCards()[0].getAttribute('aria-pressed')).toBe('true');
    expect(document.querySelectorAll('[aria-label="Tool call outcomes"]')).toHaveLength(1);
    expect(document.querySelector('[aria-label="Top tools by call count"]')?.textContent).toContain('Read');
    expect(text()).not.toContain('Overview tool');
  });

  it('preserves the period, query, loaded pages and collapsed picker when returning to the overview', async (): Promise<void> => {
    const api = activityApi();
    await render(api);
    button('30 days').click();
    await vi.waitFor(() => expect(sessionCards()).toHaveLength(2));
    submitSearch('codex');
    await vi.waitFor(() => expect(sessionCards()).toHaveLength(2));
    sessionCards()[0].click();
    await vi.waitFor(() => expect(text()).toContain('Failed tools'));
    button('Load more sessions').click();
    await vi.waitFor(() => expect(sessionCards()).toHaveLength(3));
    const details = searchDetails();
    details.open = false;
    flushSync();
    expect(text()).toContain('Failed tools');
    expect(sessionCards()[0].getAttribute('aria-pressed')).toBe('true');

    button('Back to overview').click();
    flushSync();
    expect(text()).toContain('Overview tool');
    expect(document.querySelector('[aria-label="Session statistics"]')).toBeNull();
    expect(button('30 days').getAttribute('aria-pressed')).toBe('true');
    expect(searchDetails()).toBe(details);
    expect(details.open).toBe(false);
    expect(details.querySelector('input')?.value).toBe('codex');
    expect(sessionCards()).toHaveLength(3);
    expect(sessionCards()[0].getAttribute('aria-pressed')).toBe('false');
    expect(api.overview).toHaveBeenCalledTimes(2);
    expect(api.sessions).toHaveBeenLastCalledWith({ days: 30, q: 'codex', cursor: 'next-page' }, expect.any(AbortSignal));
  });

  it('returns to MCP aggregate on an explicit source switch and discards a late session report', async (): Promise<void> => {
    const api = activityApi();
    const pending = Promise.withResolvers<ActivitySessionReport>();
    api.session.mockReturnValueOnce(pending.promise);
    await render(api);
    sessionCards()[0].click();
    flushSync();
    const signal = api.session.mock.lastCall?.[1];
    chooseSource('mcp');
    expect(signal?.aborted).toBe(true);
    expect(text()).toContain('Cancelled');
    expect(button('7 days').getAttribute('aria-pressed')).toBe('true');
    expect(document.querySelector('details')).toBeNull();
    pending.resolve(report);
    await pending.promise;
    chooseSource('harness');
    expect(text()).toContain('Overview tool');
    expect(text()).not.toContain('Session detail');
    expect(sessionCards()[0].getAttribute('aria-pressed')).toBe('false');
  });

  it('keeps a healthy empty source distinct from an unavailable one', async (): Promise<void> => {
    const api = activityApi();
    api.overview.mockResolvedValue({ ...overview, harness: { status: 'unavailable' } });
    api.sessions.mockRejectedValue(new HttpError(503, 'Unavailable', null));
    await render(api, 'mcp');
    expect(sourceControl('mcp').checked).toBe(true);
    expect(document.querySelector('[aria-label="No tool calls"]')).not.toBeNull();
    expect(text()).not.toContain('unavailable');
    chooseSource('harness');
    expect(text()).toContain('Harness activity is unavailable.');
    await vi.waitFor(() => expect(text()).toContain('Harness sessions are unavailable.'));
  });

  it('distinguishes a sessions error from an empty list', async (): Promise<void> => {
    const api = activityApi();
    api.sessions.mockRejectedValue(new HttpError(500, 'Unexpected error', null));
    await render(api);
    expect(sourceControl('harness').checked).toBe(true);
    expect(text()).toContain('Could not load harness sessions.');
  });

  it('does not infer source availability from an untyped overview failure', async (): Promise<void> => {
    const api = activityApi();
    api.overview.mockRejectedValue(new HttpError(503, 'Unavailable', null));
    await render(api);
    expect(text()).toContain('Could not load the activity summary.');
    expect(text()).not.toContain('Harness activity is unavailable.');
    expect(text()).toContain('first/path');
  });

  it('does not append a late page to a new search', async (): Promise<void> => {
    const api = activityApi();
    const activity = await render(api);
    const oldPage = Promise.withResolvers<ActivitySessionPage>();
    api.sessions.mockReturnValueOnce(oldPage.promise);
    const pending = activity.loadMore();
    const oldSignal = api.sessions.mock.lastCall?.[1];
    activity.searchSessions('no match');
    expect(oldSignal?.aborted).toBe(true);
    await vi.waitFor(() => expect(text()).toContain('No matching sessions.'));
    oldPage.resolve({ identity_key: identity, period, sessions: [third], page: { kind: 'end' } });
    await pending;
    flushSync();
    expect(text()).toContain('No matching sessions.');
    expect(text()).not.toContain('third');
  });

  it('rejects wrong-account payloads and ignores a detail that resolves after the account changes', async (): Promise<void> => {
    const api = activityApi();
    api.overview.mockResolvedValue({ ...overview, identity_key: 'wrong-account' });
    let current = identity;
    const activity = new ActivityState(api, identity, () => current);
    state = activity;
    await activity.refresh();
    expect(activity.overview.kind).toBe('error');
    const deferred = Promise.withResolvers<ActivitySessionReport>();
    api.session.mockReturnValue(deferred.promise);
    activity.selectSource('harness');
    const pending = activity.openSession(session.key);
    expect(api.session).toHaveBeenCalled();
    current = 'new-account';
    deferred.resolve(report);
    await pending;
    expect(activity.report.kind).not.toBe('ready');
  });
});
