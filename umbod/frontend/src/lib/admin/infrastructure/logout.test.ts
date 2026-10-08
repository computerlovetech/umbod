import { describe, expect, test, vi } from 'vitest';
import { BrowserLogoutNavigation, buildLogoutUrl, gatewayLogoutUrl, type LogoutNavigation } from './logout';
import { logoutConfigurationSchema, type PublicConfigurationProvider } from './public-configuration';

const configuration = { auth0Domain: 'tenant.eu.auth0.com', clientId: 'actual-client&=+"', returnTo: 'https://admin.example.test/signed-out.html' };

describe('logout navigation boundary', () => {
  test('encodes both gateway and Auth0 query boundaries with the actual client', () => {
    const destination = new URL(buildLogoutUrl(configuration), 'https://admin.example.test');
    expect(destination.pathname).toBe('/oauth2/sign_out');
    const auth0 = new URL(destination.searchParams.get('rd')!);
    expect(auth0.origin).toBe('https://tenant.eu.auth0.com');
    expect(auth0.pathname).toBe('/v2/logout');
    expect([...auth0.searchParams]).toEqual([['client_id', configuration.clientId], ['returnTo', configuration.returnTo]]);
    expect(buildLogoutUrl(configuration)).toContain('%26returnTo%3Dhttps%253A%252F%252F');
  });

  test.each([null, undefined])('uses only the fixed gateway return for absent configuration', (value) => {
    expect(buildLogoutUrl(value)).toBe(gatewayLogoutUrl);
  });

  test.each(['https://tenant.auth0.com', 'tenant.auth0.com:443', 'user@tenant.auth0.com', 'tenant.auth0.com/path', '*.auth0.com', 'tenant.auth0.com\n', '-tenant.auth0.com', 'tenant..auth0.com', 'a'.repeat(64) + '.auth0.com'])('rejects unsafe domains %s', (auth0Domain) => {
    expect(logoutConfigurationSchema.safeParse({ ...configuration, auth0Domain }).success).toBe(false);
  });

  test.each(['', 'two words', 'line\nbreak', 'nul\x00byte', 'a'.repeat(257)])('rejects unsafe clients', (clientId) => {
    expect(logoutConfigurationSchema.safeParse({ ...configuration, clientId }).success).toBe(false);
  });

  test.each(['http://admin.example.test/signed-out.html', '//evil.test/signed-out.html', 'https://user:pass@admin.example.test/signed-out.html', 'https://admin.example.test/signed-out.html?rd=evil', 'https://admin.example.test/signed-out.html#evil', 'https://admin.example.test/admin', 'https://admin.example.test/a/../signed-out.html', 'https://admin.example.test\\evil/signed-out.html', 'javascript:alert(1)'])('rejects arbitrary return destinations', (returnTo) => {
    expect(logoutConfigurationSchema.safeParse({ ...configuration, returnTo }).success).toBe(false);
  });

  test('does not navigate on construction and navigates once only after explicit invocation', async () => {
    const get = vi.fn().mockResolvedValue({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp', logout: configuration });
    const provider: PublicConfigurationProvider = { get };
    const assign = vi.fn<(url: string) => void>();
    const navigation: LogoutNavigation = new BrowserLogoutNavigation(provider, assign);
    expect(get).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
    await Promise.all([navigation.logout(), navigation.logout()]);
    expect(get).toHaveBeenCalledOnce();
    expect(assign).toHaveBeenCalledExactlyOnceWith(buildLogoutUrl(configuration));
  });

  test.each(['unavailable', 'partial', 'evil'])('configuration failure safely recovers gateway-only: %s', async (failure) => {
    const get = failure === 'unavailable'
      ? vi.fn().mockRejectedValue(new Error('unavailable'))
      : vi.fn().mockResolvedValue({ logout: failure === 'partial' ? { auth0Domain: 'tenant.auth0.com' } : { ...configuration, returnTo: 'https://evil.test/admin' } });
    const assign = vi.fn<(url: string) => void>();
    const navigation: LogoutNavigation = new BrowserLogoutNavigation({ get }, assign);
    await navigation.logout();
    expect(assign).toHaveBeenCalledExactlyOnceWith(gatewayLogoutUrl);
  });
});
