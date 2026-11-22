import { describe, expect, test } from 'vitest';
import { load } from './+page';
import { load as loadLegacyTelemetry } from './(workspace)/getting-started/telemetry/+page';
import { usesWorkspaceShell } from '#lib/workspace/navigation.js';

describe('workspace entry', () => {
  test.each(['/admin', '/admin/connectors', '/dashboard', '/connectors', '/connectors/detail', '/files', '/insights', '/insights/logs', '/getting-started', '/getting-started/telemetry', '/settings', '/settings/tokens'])('recognizes the workspace shell for %s', (pathname: string): void => {
    expect(usesWorkspaceShell(pathname)).toBe(true);
  });

  test.each(['/', '/connectors-other', '/login', '/administrator', '/getting-started-other', '/settings-other'])('does not suppress the application header for %s', (pathname: string): void => {
    expect(usesWorkspaceShell(pathname)).toBe(false);
  });
  test.each(['', '?tab=tokens#setup'])('redirects legacy telemetry bookmarks to Tokens (%s)', (suffix: string): void => {
    const url = new URL(`https://umbod.test/getting-started/telemetry${suffix}`);
    expect(() => loadLegacyTelemetry({ url })).toThrow(expect.objectContaining({ status: 307, location: `/settings/tokens${suffix}` }));
  });

  test('root redirects temporarily to the dashboard', async (): Promise<void> => {
    await expect(async () => load({} as never)).rejects.toMatchObject({ status: 307, location: '/dashboard' });
  });
});
