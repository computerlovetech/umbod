import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { afterEach, describe, expect, test, vi } from 'vitest';
import WorkspaceShell from './WorkspaceShell.svelte';
import { WorkspaceShellState, type WorkspaceNavigationContext } from './workspace-shell-state.svelte';

const navigating = vi.hoisted(() => ({
  to: null as { url: URL } | null,
  from: null as { url: URL } | null
}));
vi.mock('$app/state', () => ({ navigating }));
afterEach((): void => { navigating.to = null; navigating.from = null; });

const navigationItems = [
  { id: 'dashboard', label: 'Dashboard', href: '/dashboard' },
  { id: 'tools', label: 'Tools', href: '/tools' }
];

describe('workspace shell public interface', () => {
  test('renders only supplied navigation with neutral account fallback and wide content', () => {
    const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
    const { body } = render(WorkspaceShell, { props: {
      workspaceLabel: 'Workspace', homeHref: '/dashboard', navigationItems,
      activeItem: 'dashboard', accountFallback: 'Signed in', contentWidth: 'wide',
      children: createRawSnippet(() => ({ render: (): string => '<p>Catalogue</p>' })),
      logout: { logout }
    } });
    expect(body).toContain('Workspace sidebar');
    expect(body).toContain('Workspace navigation');
    expect(body).toContain('href="/dashboard"');
    expect(body).toContain('aria-current="page"');
    expect(body).toContain('Signed in');
    expect(body).toContain('content-width wide');
    expect(body).toContain('Catalogue');
    expect(body).not.toContain('/admin');
    expect(body).not.toContain('Administration');
    expect(logout).not.toHaveBeenCalled();
  });

  test.each([false, true])('explicit content loading marks the whole main view busy: %s', (contentLoading): void => {
    const { body } = render(WorkspaceShell, { props: {
      workspaceLabel: 'Workspace', homeHref: '/dashboard', navigationItems,
      activeItem: 'dashboard', contentLoading,
      children: createRawSnippet(() => ({ render: (): string => '<p>Catalogue</p>' }))
    } });
    expect(body).toContain(`aria-busy="${contentLoading}"`);
    expect(body.includes('content-loading active')).toBe(contentLoading);
    expect(body.includes(' inert')).toBe(contentLoading);
    expect(body).toContain('Workspace sidebar');
  });

  test('pending navigation follows supplied links without marking unrelated or same-page navigation busy', () => {
    let context: WorkspaceNavigationContext = {
      activeItem: 'dashboard', navigationItems, destinationPath: null, originPath: '/dashboard'
    };
    const state = new WorkspaceShellState(() => context);
    expect(state.displayedActiveItem).toBe('dashboard');
    context = { ...context, destinationPath: '/tools' };
    expect(state.pendingNavigationItem?.id).toBe('tools');
    expect(state.displayedActiveItem).toBe('tools');
    context = { ...context, destinationPath: '/unrelated' };
    expect(state.pendingNavigationItem).toBeUndefined();
    context = { ...context, destinationPath: '/dashboard' };
    expect(state.pendingNavigationItem).toBeUndefined();
    context = { ...context, destinationPath: '/tools', originPath: '/tools' };
    expect(state.pendingNavigationItem).toBeUndefined();
  });

  test.each([
    ['/admin/group-permissions/connectors', '/admin/group-permissions/filesystem', true],
    ['/admin/group-permissions/filesystem', '/admin/group-permissions/connectors', true],
    ['/admin/group-permissions/connectors', '/admin/group-permissions/connectors', false]
  ] as const)('permission navigation from %s to %s marks the content busy: %s', (origin, destination, busy): void => {
    navigating.from = { url: new URL(origin, 'https://umbod.test') };
    navigating.to = { url: new URL(destination, 'https://umbod.test') };
    const { body } = render(WorkspaceShell, { props: {
      workspaceLabel: 'Workspace', homeHref: '/dashboard',
      navigationItems: [{ id: 'groupPermissions', label: 'Group permissions', href: '/admin/group-permissions/connectors' }],
      activeItem: 'groupPermissions',
      children: createRawSnippet(() => ({ render: (): string => '<p>Permissions</p>' }))
    } });
    expect(body).toContain(`aria-busy="${busy}"`);
    expect(body.includes('content-loading active')).toBe(busy);
    expect(body.includes(' inert')).toBe(busy);
    expect(body).toContain('aria-current="page">Group permissions');
  });

  test.each([
    ['/admin/group-permissions/connectors', '/admin/group-permissions/filesystem', false],
    ['/admin/group-permissions/filesystem', '/admin/group-permissions/connectors', false],
    ['/admin/group-permissions/connectors', '/admin/groups', true],
    ['/admin/groups', '/admin/group-permissions/filesystem', true],
    ['/admin/group-permissions-other', '/admin/group-permissions/filesystem', true]
  ] as const)('scoped navigation from %s to %s marks shell pending: %s', (originPath, destinationPath, pending): void => {
    const state = new WorkspaceShellState(() => ({
      activeItem: 'groupPermissions', navigationItems, originPath, destinationPath,
      navigationScope: '/admin/group-permissions'
    }));
    expect(state.navigationPending).toBe(pending);
  });

  test('explicit logout blocks duplicate submissions', async () => {
    const state = new WorkspaceShellState(() => ({
      activeItem: 'dashboard', navigationItems, destinationPath: null, originPath: null
    }));
    const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
    expect(state.loggingOut).toBe(false);
    await Promise.all([state.logout({ logout }), state.logout({ logout })]);
    expect(state.loggingOut).toBe(true);
    expect(logout).toHaveBeenCalledOnce();
  });
});
