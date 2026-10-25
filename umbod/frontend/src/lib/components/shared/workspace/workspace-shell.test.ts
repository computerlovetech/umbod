import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { describe, expect, test, vi } from 'vitest';
import WorkspaceShell from './WorkspaceShell.svelte';
import { WorkspaceShellState, type WorkspaceNavigationContext } from './workspace-shell-state.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

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
