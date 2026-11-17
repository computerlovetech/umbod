import { describe, expect, test, vi } from 'vitest';
import { load } from './+layout';

vi.mock('#lib/admin/infrastructure/public-configuration.js', () => ({
  publicConfigurationProvider: { get: async (): Promise<object> => ({ apiBaseUrl: '/api' }) }
}));

describe('Getting started loader', () => {
  test('resolves one installer base without requesting or awaiting administration access', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise(() => {}));
    await expect(load({ fetch, url: new URL('https://site.test/getting-started') } as never)).resolves.toEqual({
      installerBaseUrl: 'https://site.test/api/install/v1'
    });
    expect(fetch).not.toHaveBeenCalled();
  });
});
