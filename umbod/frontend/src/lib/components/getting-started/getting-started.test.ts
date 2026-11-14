import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';
import { workspaceNavigation } from '$lib/workspace/navigation';
import GettingStarted from './GettingStarted.svelte';

vi.mock('$lib/components/feedback', () => ({
  useToast: (): ToastApi => ({
    success: (): number => 1, warning: (): number => 1, error: (): number => 1,
    dismiss: (): void => {}
  })
}));

describe('unified Getting started page', () => {
  test.each([true, false])('is available in the shared navigation with administration=%s', (administration): void => {
    const items = workspaceNavigation(administration);
    expect(items.filter((item) => item.id === 'gettingStarted')).toEqual([
      { id: 'gettingStarted', label: 'Getting started', href: '/getting-started', icon: 'gettingStarted' }
    ]);
    expect(items.some((item) => item.href.includes('mcp-setup'))).toBe(false);
  });

  test.each(['connect', 'telemetry'] as const)('renders only the %s subpage within one workspace and heading', (activePage): void => {
    const body = render(GettingStarted, { props: { activePage, installerBaseUrl: 'https://site.test/api/install/v1' } }).body;
    expect(body.match(/<h1[\s>]/g)).toHaveLength(1);
    expect(body).toContain('Getting started</h1>');
    expect(body.match(/aria-label="Workspace sidebar"/g)).toHaveLength(1);
    expect(body).toContain('href="/getting-started"');
    expect(body).toContain('href="/getting-started/telemetry"');
    expect(body.includes('aria-label="Harness setup guides"')).toBe(activePage === 'connect');
    expect(body.includes('aria-label="Telemetry setup"')).toBe(activePage === 'telemetry');
    expect(body.includes('https://site.test/api/install/v1/codex/install.sh')).toBe(activePage === 'connect');
    expect(body).toContain('aria-current="page"');
    expect(body).not.toContain('href="/admin"');
  });
});
