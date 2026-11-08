import { describe, expect, test, vi } from 'vitest';
import { load } from './+layout';

vi.mock('$lib/admin/infrastructure/public-configuration', () => ({
  publicConfigurationProvider: { get: async (): Promise<object> => ({ apiBaseUrl: '/api', mcpBaseUrl: 'https://umbod.test/' }) }
}));

describe('Getting started loader', () => {
  test('resolves the MCP endpoint without requesting or awaiting administration access', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise(() => {}));
    await expect(load({ fetch, url: new URL('https://site.test/getting-started') } as never)).resolves.toEqual({ mcpEndpoint: 'https://umbod.test/mcp' });
    expect(fetch).not.toHaveBeenCalled();
  });
});
