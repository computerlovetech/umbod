import { render } from 'svelte/server';
import { Window } from 'happy-dom';
import { createRawSnippet } from 'svelte';
import { describe, expect, test, vi } from 'vitest';
import AdminShell from './AdminShell.svelte';
import AppHeader from '../header/AppHeader.svelte';
import { WorkspaceNavigationHistory } from '$lib/workspace/navigation-history.svelte';
import { workspaceNavigationHistoryKey } from '$lib/workspace/navigation-history-context';
import { currentUserIdentitySchema, createHeaderAccountUserInfoBoundary } from '../../header/accountIdentity';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

describe('admin shell logout', () => {
  test('nullable email hides only its row in both account presentations', () => {
    const profile = currentUserIdentitySchema.parse({
      id: 'admin-id', email: null, name: 'unknown', picture: 'https://example.com/admin.png'
    });
    const accountIdentity = createHeaderAccountUserInfoBoundary().viewHeaderAccountIdentity(profile);
    const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
    const header = render(AppHeader, { props: { accountIdentity } });
    const shell = render(AdminShell, { props: {
      activeItem: 'connectors', accountIdentity, logout: { logout },
      children: createRawSnippet(() => ({ render: (): string => '<p>Content</p>' }))
    } });
    for (const { body } of [header, shell]) {
      expect(body).toContain('unknown');
      expect(body).toContain('https://example.com/admin.png');
      expect(body).not.toContain('class="account-email');
      expect(body).not.toContain('admin-id');
    }
    const document = new Window().document;
    document.body.innerHTML = shell.body;
    expect(document.querySelector('button')?.textContent).toBe('Log out');
    expect(document.querySelector('button')?.type).toBe('button');
    expect(shell.body).toContain('aria-label="Administration sidebar"');
    expect(shell.body).toContain('aria-label="Administration navigation"');
    expect(document.querySelector('.workspace-back')?.textContent).toBe('←Back to workspace');
    expect(document.querySelector('.workspace-back')?.getAttribute('href')).toBe('/dashboard');
    expect(document.querySelector('nav')?.textContent).not.toContain('Dashboard');
    expect(document.querySelector('nav')?.textContent).not.toContain('Getting started');
    expect(shell.body).toContain('href="/dashboard"');
    expect(shell.body).not.toContain('Administration</a>');
    expect(shell.body).not.toContain('href="/admin"');
    expect(shell.body).toContain('href="/admin/analytics"');
    expect(shell.body).toContain('href="/admin/connectors"');
    expect(shell.body).toContain('href="/admin/group-permissions/connectors"');
    expect(shell.body).not.toContain('href="/admin/group-permissions"');
    expect(shell.body).not.toContain('href="/admin/filesystem"');
    expect(shell.body).not.toContain('Filesystem</a>');
    expect(Array.from(document.querySelectorAll('nav a'), (link): string => link.textContent.trim())).toEqual([
      'Connectors', 'Groups', 'Group permissions', 'Log analytics', 'Instance settings'
    ]);
    expect(document.querySelector('nav a[aria-current="page"]')?.textContent.trim()).toBe('Connectors');
    expect(document.querySelector('h1')).toBeNull();
    expect(shell.body).toContain('Content');
    expect(logout).not.toHaveBeenCalled();
  });

  test('returns to the last workspace location supplied by the application root', (): void => {
    const history = new WorkspaceNavigationHistory(new URL('https://umbod.test/getting-started/telemetry?tab=tokens#setup'), true);
    history.startNavigation(new URL('https://umbod.test/getting-started/telemetry?tab=tokens#setup'), new URL('https://umbod.test/admin/groups'), true);
    const { body } = render(AdminShell, {
      context: new Map([[workspaceNavigationHistoryKey, history]]),
      props: {
        activeItem: 'groups', accountIdentity: { kind: 'hidden' },
        children: createRawSnippet(() => ({ render: (): string => '<h1>Unchanged page</h1>' }))
      }
    });
    const document = new Window().document;
    document.body.innerHTML = body;
    expect(document.querySelector('.workspace-back')?.getAttribute('href')).toBe('/getting-started/telemetry?tab=tokens#setup');
    expect(document.querySelector('.enter-forward')).not.toBeNull();
    expect(document.querySelector('h1')?.textContent).toBe('Unchanged page');
  });

  test('current-user contract requires explicit nullable email', () => {
    expect(currentUserIdentitySchema.safeParse({ id: 'admin-id', name: 'unknown' }).success).toBe(false);
    expect(currentUserIdentitySchema.safeParse({ id: 'admin-id', name: 'unknown', email: 123 }).success).toBe(false);
  });

  test.each(['visible', 'hidden'] as const)('offers an explicit logout independent of %s identity without automatic navigation', (kind) => {
    const logout = vi.fn<() => Promise<void>>().mockResolvedValue();
    const { body } = render(AdminShell, { props: {
      activeItem: 'connectors',
      accountIdentity: kind === 'visible' ? { kind, name: 'Administrator', email: 'admin@example.test', picture: null, hiddenValues: { id: 'admin-id' } } : { kind },
      children: createRawSnippet(() => ({ render: (): string => '<p>Content</p>' })),
      logout: { logout }
    } });
    const document = new Window().document;
    document.body.innerHTML = body;
    expect(document.querySelector('button')?.type).toBe('button');
    expect(document.querySelector('button')?.textContent).toBe('Log out');
    expect(logout).not.toHaveBeenCalled();
  });
});
