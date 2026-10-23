import { describe, expect, test, vi } from 'vitest';
import { load } from './+page';

vi.mock('$lib/admin/infrastructure/public-configuration', () => ({
  publicConfigurationProvider: { get: async (): Promise<object> => ({ apiBaseUrl: '/api', mcpBaseUrl: 'https://umbod.test/' }) }
}));

describe('dashboard loader', () => {
  test('resolves the catalogue page without requesting or awaiting administration access', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise(() => {}));
    await expect(load({ fetch } as never)).resolves.toEqual({ mcpEndpoint: 'https://umbod.test/mcp' });
    expect(fetch).not.toHaveBeenCalled();
  });
});
