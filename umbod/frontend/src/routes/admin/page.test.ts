import { describe, expect, test, vi } from 'vitest';
import { workspaceNavigation } from '$lib/workspace/navigation';
import { load } from './+page';

describe('administration entry', (): void => {
  test('redirects old overview bookmarks to connectors without fetching overview data', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    await expect(async (): Promise<unknown> => load({ fetch } as never)).rejects.toMatchObject({ status: 307, location: '/admin/connectors' });
    expect(fetch).not.toHaveBeenCalled();
  });

  test('retains administrative destinations without an overview navigation entry', (): void => {
    const links = workspaceNavigation(true);
    expect(links.some((link): boolean => link.id === 'overview' || link.href === '/admin')).toBe(false);
    expect(links.map((link): string => link.href)).toEqual([
      '/dashboard', '/connectors', '/files', '/getting-started', '/admin/connectors'
    ]);
  });
});
