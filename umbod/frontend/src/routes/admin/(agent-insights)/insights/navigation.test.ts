import { describe, expect, test } from 'vitest';
import { load as insights } from './+page';
import { load as behaviour } from '../../agent-behaviour/+page';
import { load as analytics } from '../../analytics/+page';
import { load as diagnostics } from '../agent-diagnostics/+page';
import { load as configuration } from './agent-behaviour/configuration/+page';
import { InsightsNavigation } from '#lib/components/admin/insights/insights-navigation.js';

describe('Insights navigation', (): void => {
  test.each([
    { load: insights, source: '/admin/insights', target: '/admin/insights/agent-behaviour' },
    { load: behaviour, source: '/admin/agent-behaviour', target: '/admin/insights/agent-behaviour' },
    { load: analytics, source: '/admin/analytics', target: '/admin/insights/logs' }
  ])('redirects $source while preserving query and fragment', async ({ load, source, target }): Promise<void> => {
    const suffix = '?filter=one&filter=two#results';
    const url = new URL(`https://umbod.test${source}${suffix}`);
    if (load === insights) {
      Object.defineProperty(url, 'hash', { get(): never { throw new Error('The router does not expose url.hash in load'); } });
    }
    await expect(async () => load({ url } as never)).rejects.toMatchObject({ status: 307, location: target + suffix });
  });

  test.each(['', '?tab=patterns', '?tab=unknown&filter=a'])('serves standalone patterns at /admin/agent-diagnostics%s', (query): void => {
    const url = new URL(`https://umbod.test/admin/agent-diagnostics${query}#patterns`);
    expect(diagnostics({ url } as never)).toBeUndefined();
  });

  test.each([
    { load: diagnostics, source: '/admin/agent-diagnostics?tab=reporting', target: '/admin/system-settings?section=agent-diagnostics' },
    { load: diagnostics, source: '/admin/agent-diagnostics?section=filesystem&tab=reporting&filter=a&filter=b', target: '/admin/system-settings?section=agent-diagnostics&filter=a&filter=b' },
    { load: configuration, source: '/admin/insights/agent-behaviour/configuration', target: '/admin/agent-diagnostics' },
    { load: configuration, source: '/admin/insights/agent-behaviour/configuration?tab=patterns&filter=a&filter=b', target: '/admin/agent-diagnostics?filter=a&filter=b' },
    { load: configuration, source: '/admin/insights/agent-behaviour/configuration?tab=reporting&section=filesystem&filter=a&filter=b', target: '/admin/system-settings?section=agent-diagnostics&filter=a&filter=b' }
  ])('redirects $source to $target while preserving the fragment', async ({ load, source, target }): Promise<void> => {
    const url = new URL(`https://umbod.test${source}#results`);
    Object.defineProperty(url, 'hash', { get(): never { throw new Error('The router does not expose url.hash in load'); } });
    await expect(async () => load({ url } as never)).rejects.toMatchObject({ status: 307, location: `${target}#results` });
  });

  test('selects the current Insights view', (): void => {
    let pathname = '/admin/insights/agent-behaviour';
    const navigation = new InsightsNavigation(() => pathname);
    expect(navigation.activeId).toBe('behaviour');
    pathname = '/admin/insights/logs';
    expect(navigation.activeId).toBe('logs');
    expect(navigation.diagnostics).toBe(false);
    pathname = '/admin/agent-diagnostics';
    expect(navigation.diagnostics).toBe(true);
  });
});
