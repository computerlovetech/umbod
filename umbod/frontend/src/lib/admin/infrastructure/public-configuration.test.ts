import { describe, expect, test, vi } from 'vitest';
import { BrowserPublicConfigurationProvider, InMemoryPublicConfigurationProvider, publicConfigurationSchema } from './public-configuration';

describe('public browser configuration', () => {
  test('loads validated public deployment keys once for concurrent consumers', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ apiBaseUrl: '/api', mcpBaseUrl: 'https://mcp.example.test' }));
    const provider = new BrowserPublicConfigurationProvider(request);
    const configurations = await Promise.all([provider.get(), provider.get()]);
    expect(configurations).toEqual([{ apiBaseUrl: '/api', mcpBaseUrl: 'https://mcp.example.test' }, { apiBaseUrl: '/api', mcpBaseUrl: 'https://mcp.example.test' }]);
    expect(request).toHaveBeenCalledOnce();
    expect(request).toHaveBeenCalledWith('/app-config.json', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }));
  });
  test.each(['//external.example.test', 'javascript:alert(1)', '/api?token=secret', '/api#fragment'])('rejects unsafe bases %s', (apiBaseUrl) => {
    expect(publicConfigurationSchema.safeParse({ apiBaseUrl, mcpBaseUrl: 'http://localhost:8011' }).success).toBe(false);
  });
  test('loads public logout configuration through the existing provider port', async () => {
    const logout = { auth0Domain: 'tenant.auth0.com', clientId: 'actual-client', returnTo: 'https://admin.example.test/signed-out.html' };
    const provider = new BrowserPublicConfigurationProvider(vi.fn<typeof fetch>().mockResolvedValue(Response.json({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp', logout })));
    expect((await provider.get()).logout).toEqual(logout);
    expect(publicConfigurationSchema.parse({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp', logout: null }).logout).toBeNull();
  });
  test.each([{}, { auth0Domain: 'tenant.auth0.com' }, { auth0Domain: 'tenant.auth0.com', clientId: 'actual-client' }])('rejects partial logout configuration', (logout) => {
    expect(publicConfigurationSchema.safeParse({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp', logout }).success).toBe(false);
  });
  test('in-memory configuration satisfies the same validated port', async () => {
    expect(await new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: 'http://localhost:8011' }).get()).toEqual({ apiBaseUrl: '/api', mcpBaseUrl: 'http://localhost:8011' });
  });
});
