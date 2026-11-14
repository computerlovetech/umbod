import { afterEach, expect, test, vi } from 'vitest';
import { InMemoryAgentBehaviourApi, deferred } from '$lib/agent-behaviour/in-memory.test-support';
import { InMemoryLogCounts } from '$lib/admin/analytics/in-memory.test-support';
import type { LogCountResponse } from '$lib/admin/analytics/domain/schemas';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InsightsState } from './insights-state.svelte';
import { configuration } from './insights.test-support.svelte';

afterEach((): void => { vi.restoreAllMocks(); });

test('behaviour access loss fences analytics already in flight and destroys cached drafts', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi(); api.current = configuration();
  const logs = new InMemoryLogCounts();
  const response = deferred<LogCountResponse>(); logs.handler = (): Promise<LogCountResponse> => response.promise;
  const state = new InsightsState(api, logs);
  await state.behaviour.configuration.load();
  state.behaviour.configuration.updatePattern('missing-context', 'name', 'Unsaved');
  const analytics = state.createAnalytics();
  const running = analytics.run();
  vi.spyOn(api.reports, 'list').mockRejectedValue(new HttpError(403, 'Forbidden', null));
  await state.behaviour.reports.load();
  expect(state.allowed).toBe(false);
  expect(state.behaviour.configuration.patterns).toEqual([]);
  expect(logs.signals[0]?.aborted).toBe(true);
  response.resolve({ rows: [{ bucket: { kind: 'none' }, groups: [], count: 99 }], has_more: false });
  await running;
  expect(analytics.result).toBeUndefined();
  state.dispose();
});

test('leaving Insights aborts work and clears state before obsolete configuration reads resolve', async (): Promise<void> => {
  const api = new InMemoryAgentBehaviourApi();
  const response = deferred<ReturnType<typeof configuration>>();
  vi.spyOn(api.configuration, 'get').mockImplementation((): Promise<ReturnType<typeof configuration>> => response.promise);
  const state = new InsightsState(api, new InMemoryLogCounts());
  state.start(); state.dispose();
  response.resolve(configuration());
  await response.promise;
  expect(state.allowed).toBe(false);
  expect(state.behaviour.configuration.loaded).toBe(false);
  expect(state.behaviour.configuration.patterns).toEqual([]);
});
