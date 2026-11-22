import { describe, expect, test } from 'vitest';
import { load as insights } from './+page';
import { load as behaviour } from '../../agent-behaviour/+page';
import { load as analytics } from '../../analytics/+page';
import { load as configuration } from './agent-behaviour/configuration/+page';
import { InsightsNavigation } from '#lib/components/admin/insights/insights-navigation.js';

describe('Insights navigation', (): void => {
  test.each([
    { load: insights, source: '/admin/insights', target: '/admin/insights/agent-behaviour' },
    { load: behaviour, source: '/admin/agent-behaviour', target: '/admin/insights/agent-behaviour' },
    { load: analytics, source: '/admin/analytics', target: '/admin/insights/logs' },
    { load: configuration, source: '/admin/insights/agent-behaviour/configuration', target: '/admin/agent-diagnostics' }
  ])('redirects $source while preserving query and fragment', async ({ load, source, target }): Promise<void> => {
    const suffix = '?filter=one&filter=two#results';
    const url = new URL(`https://umbod.test${source}${suffix}`);
    if (load === insights || load === configuration) {
      Object.defineProperty(url, 'hash', { get(): never { throw new Error('The router does not expose url.hash in load'); } });
    }
    await expect(async () => load({ url } as never)).rejects.toMatchObject({ status: 307, location: target + suffix });
  });

  test('recognizes Agent diagnostics separately from the Insights views', (): void => {
    let pathname = '/admin/insights/agent-behaviour';
    const navigation = new InsightsNavigation(() => pathname);
    expect(navigation.activeId).toBe('behaviour');
    expect(navigation.diagnostics).toBe(false);
    pathname = '/admin/agent-diagnostics';
    expect(navigation.diagnostics).toBe(true);
    pathname = '/admin/insights/logs';
    expect(navigation.activeId).toBe('logs');
    expect(navigation.diagnostics).toBe(false);
  });
});
