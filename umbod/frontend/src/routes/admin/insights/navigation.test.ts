import { describe, expect, test } from 'vitest';
import { load as insights } from './+page';
import { load as behaviour } from '../agent-behaviour/+page';
import { load as analytics } from '../analytics/+page';
import { InsightsNavigation } from '$lib/components/admin/insights/insights-navigation';

describe('Insights navigation', (): void => {
  test.each([
    { load: insights, source: '/admin/insights', target: '/admin/insights/agent-behaviour' },
    { load: behaviour, source: '/admin/agent-behaviour', target: '/admin/insights/agent-behaviour' },
    { load: analytics, source: '/admin/analytics', target: '/admin/insights/logs' }
  ])('redirects $source while preserving query and fragment', async ({ load, source, target }): Promise<void> => {
    const suffix = '?filter=one&filter=two#results';
    await expect(async () => load({ url: new URL(`https://umbod.test${source}${suffix}`) } as never)).rejects.toMatchObject({ status: 307, location: target + suffix });
  });

  test('keeps Configuration in the Agent behaviour location without a competing route state', (): void => {
    let pathname = '/admin/insights/agent-behaviour';
    const navigation = new InsightsNavigation(() => pathname);
    expect(navigation.activeId).toBe('behaviour');
    expect(navigation.configuration).toBe(false);
    pathname = '/admin/insights/agent-behaviour/configuration';
    expect(navigation.activeId).toBe('behaviour');
    expect(navigation.configuration).toBe(true);
    pathname = '/admin/insights/logs';
    expect(navigation.activeId).toBe('logs');
    expect(navigation.configuration).toBe(false);
  });
});
