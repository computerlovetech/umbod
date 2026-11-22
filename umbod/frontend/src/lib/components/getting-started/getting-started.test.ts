import { renderWorkspace } from '#lib/components/workspace/render-workspace.test-support.js';
import { describe, expect, test, vi } from 'vitest';
import type { ToastApi } from '#lib/components/feedback/toast-state.svelte.js';
import { workspaceNavigation } from '#lib/workspace/navigation.js';
import GettingStarted from './GettingStarted.svelte';

vi.mock('#lib/components/feedback/index.js', () => ({
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

  test('renders the installer wizard without token management in the workspace', (): void => {
    const body = renderWorkspace(GettingStarted, { props: { installerBaseUrl: 'https://site.test/api/install/v1' } }, '/getting-started').body;
    expect(body.match(/<h1[\s>]/g)).toHaveLength(1);
    expect(body).toContain('Getting started</h1>');
    expect(body.match(/aria-label="Workspace sidebar"/g)).toHaveLength(1);
    expect(body).toContain('href="/getting-started"');
    expect(body).not.toContain('href="/getting-started/telemetry"');
    expect(body).toContain('aria-label="Installer steps"');
    expect(body).toContain('Choose your platform');
    expect(body).not.toContain('Telemetry tokens');
    expect(body).toContain('aria-current="page"');
    expect(body).not.toContain('href="/admin"');
  });
});
