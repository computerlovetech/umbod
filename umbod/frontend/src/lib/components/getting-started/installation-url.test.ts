import { describe, expect, test } from 'vitest';
import { normalizeInstallationUrl, resolveInstallerBaseUrl } from './installation-url';

describe('installer URL validation', (): void => {
  test.each([
    ['https://umbod.test/api/install/v1/', 'https://umbod.test/api/install/v1'],
    ['https://umbod.test/team/api/install/v1', 'https://umbod.test/team/api/install/v1'],
    ['http://localhost:3010/api/install/v1', 'http://localhost:3010/api/install/v1'],
    ['http://127.0.0.1:8000/api/install/v1', 'http://127.0.0.1:8000/api/install/v1'],
    ['http://[::1]:8000/api/install/v1', 'http://[::1]:8000/api/install/v1']
  ])('normalizes %s without losing deployment paths', (input: string, expected: string): void => {
    expect(normalizeInstallationUrl(input)).toBe(expected);
  });

  test.each([
    '', '/install/v1', 'file:///install/v1', 'https://', 'https:///umbod.test/install/v1', 'https://umbod.test:invalid',
    'https://user:secret@umbod.test', 'https://user@umbod.test', 'https://@umbod.test',
    'https://umbod.test/install/v1?token=secret', 'https://umbod.test/install/v1?', 'https://umbod.test/install/v1#',
    ' https://umbod.test', 'https://umbod.test/\ninstall', 'https://umbod.test/\u0000install',
    'http://umbod.test', 'http://localhost.evil.test', 'http://127.1', 'http://127.000.0.1',
    'https://${UMBOD_HOST}', 'https://umbod.test\\@other.test'
  ])('rejects unsafe installer URL %j', (url: string): void => {
    expect(() => normalizeInstallationUrl(url)).toThrow();
  });

  test.each([
    ['/api', 'https://site.test/api/install/v1'],
    ['/api/', 'https://site.test/api/install/v1'],
    ['https://api.test/api', 'https://api.test/api/install/v1'],
    ['/gateway', 'https://site.test/gateway/install/v1']
  ])('resolves configured public API base %s', (api, expected): void => {
    expect(resolveInstallerBaseUrl(api, new URL('https://site.test/getting-started'))).toBe(expected);
  });
});
