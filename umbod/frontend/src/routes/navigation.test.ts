import { describe, expect, test } from 'vitest';
import { load } from './+page';
import { usesWorkspaceShell } from '$lib/workspace/navigation';

describe('workspace entry', () => {
  test.each(['/admin', '/admin/connectors', '/dashboard', '/connectors', '/connectors/detail', '/files', '/getting-started', '/getting-started/telemetry'])('recognizes the workspace shell for %s', (pathname: string): void => {
    expect(usesWorkspaceShell(pathname)).toBe(true);
  });

  test.each(['/', '/connectors-other', '/login', '/administrator', '/getting-started-other'])('does not suppress the application header for %s', (pathname: string): void => {
    expect(usesWorkspaceShell(pathname)).toBe(false);
  });
  test('root redirects temporarily to the dashboard', async (): Promise<void> => {
    await expect(async () => load({} as never)).rejects.toMatchObject({ status: 307, location: '/dashboard' });
  });
});
