import { afterEach, describe, expect, test, vi } from 'vitest';
import { createRawSnippet, mount, tick, unmount } from 'svelte';
import { administrationNavigation, workspaceNavigation, workspacePresentation } from '#lib/workspace/navigation.js';
import { WorkspaceNavigationHistory } from '#lib/workspace/navigation-history.svelte.js';
import { workspaceNavigationHistoryKey } from '#lib/workspace/navigation-history-context.js';
import { SidebarPreference, sidebarPreferenceKey } from '#lib/workspace/sidebar-preference.svelte.js';
import AdminShell from '#lib/components/admin/AdminShell.svelte';
import WorkspaceShell from './WorkspaceShell.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

describe('contextual sidebar rendering', (): void => {
  test.each([false, true])('the desktop toggle preserves only eligible destinations and focus: administration %s', async (allowed: boolean): Promise<void> => {
    component = mount(WorkspaceShell, {
      target: document.body,
      props: {
        ...workspacePresentation, navigationItems: workspaceNavigation(allowed), activeItem: 'files',
        children: createRawSnippet(() => ({ render: (): string => '<h1>Files</h1>' }))
      }
    });
    await tick();
    const toggle = document.querySelector<HTMLButtonElement>('button[aria-label="Collapse sidebar"]')!;
    expect(toggle).not.toBeNull();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const sidebar = document.getElementById(toggle.getAttribute('aria-controls')!);
    expect(sidebar?.tagName).toBe('ASIDE');
    expect(sidebar?.contains(toggle)).toBe(true);
    toggle.focus();
    toggle.click();
    await tick();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.getAttribute('aria-label')).toBe('Expand sidebar');
    expect(document.activeElement).toBe(toggle);
    expect(sidebar?.querySelector('a[title="Umbod"]')?.getAttribute('href')).toBe('/dashboard');
    expect(sidebar?.querySelector('nav a[title="Files"][aria-current="page"]')?.textContent.trim()).toBe('Files');
    expect(Boolean(sidebar?.querySelector('nav a[title="Administration"]'))).toBe(allowed);
    toggle.click();
    await tick();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(document.activeElement).toBe(toggle);
  });

  test('the root preference retains icon-rail controls when replacing the workspace shell with administration', async (): Promise<void> => {
    const context = new Map([[sidebarPreferenceKey, new SidebarPreference()]]);
    const children = createRawSnippet(() => ({ render: (): string => '<p>Existing page</p>' }));
    component = mount(WorkspaceShell, {
      target: document.body, context,
      props: { ...workspacePresentation, navigationItems: workspaceNavigation(true), activeItem: 'files', children }
    });
    await tick();
    const collapse = document.querySelector<HTMLButtonElement>('button[aria-label="Collapse sidebar"]')!;
    expect(collapse).not.toBeNull();
    collapse.click();
    await tick();
    await unmount(component);
    component = mount(AdminShell, {
      target: document.body, context,
      props: { activeItem: 'namespaces', accountIdentity: { kind: 'hidden' }, children }
    });
    await tick();
    expect(document.querySelector('button[aria-label="Expand sidebar"]')?.getAttribute('aria-expanded')).toBe('false');
    const sidebar = document.querySelector('aside');
    expect(sidebar?.querySelector('a[title="Back to workspace"]')?.getAttribute('href')).toBe('/dashboard');
    expect(sidebar?.querySelector('nav a[title="Shared namespaces"][aria-current="page"]')?.getAttribute('href')).toBe('/admin/namespaces');
    const account = sidebar?.querySelector<HTMLButtonElement>('button[aria-label="Account menu"]')!;
    expect(account?.querySelector('svg')).not.toBeNull();
    account.focus();
    account.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    await tick();
    await Promise.resolve();
    expect(account.getAttribute('aria-expanded')).toBe('true');
    expect(document.activeElement?.getAttribute('href')).toBe('/settings');
    expect(sidebar?.querySelector('[role="menuitem"][href="/settings/tokens"]')).not.toBeNull();
  });
  test.each([false, true])('workspace renders preview icons and only eligible navigation: administration %s', async (allowed: boolean): Promise<void> => {
    component = mount(WorkspaceShell, {
      target: document.body,
      props: {
        ...workspacePresentation,
        navigationItems: workspaceNavigation(allowed), activeItem: 'files',
        children: createRawSnippet(() => ({ render: (): string => '<h1>Existing files page</h1>' }))
      }
    });
    await tick();
    const links = Array.from(document.querySelectorAll('nav a'));
    expect(links.map((link): string => link.textContent.trim())).toEqual(allowed
      ? ['Dashboard', 'Connectors', 'Files', 'Insights', 'Getting started', 'Administration']
      : ['Dashboard', 'Connectors', 'Files', 'Insights', 'Getting started']);
    for (const link of links) {
      expect(link.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
      expect(link.querySelector('svg')?.getAttribute('focusable')).toBe('false');
    }
    expect(document.querySelectorAll('nav a[aria-current="page"]')).toHaveLength(1);
    expect(document.querySelector('nav a[aria-current="page"]')?.getAttribute('href')).toBe('/files');
    expect(document.querySelector('a.section-start')?.getAttribute('href')).toBe(allowed ? '/admin/connectors' : undefined);
    expect(document.querySelector('.workspace-back')).toBeNull();
    expect(document.querySelector('h1')?.textContent).toBe('Existing files page');
  });

  test.each(['connectors', 'groups', 'namespaces', 'groupPermissions', 'agentTokens', 'insights', 'agentDiagnostics', 'systemSettings'] as const)('administration selects %s while preserving the page and identity frame', async (activeItem): Promise<void> => {
    component = mount(AdminShell, {
      target: document.body,
      props: {
        activeItem, accountIdentity: { kind: 'hidden' },
        children: createRawSnippet(() => ({ render: (): string => '<h1>Existing admin page</h1>' }))
      }
    });
    await tick();
    const links = Array.from(document.querySelectorAll('nav[aria-label="Administration navigation"] a'));
    expect(links.map((link): string | null => link.getAttribute('href'))).toEqual([
      '/admin/connectors', '/admin/groups', '/admin/namespaces', '/admin/group-permissions/connectors',
      '/admin/agent-tokens', '/admin/insights/agent-behaviour', '/admin/agent-diagnostics', '/admin/system-settings'
    ]);
    expect(document.querySelectorAll('nav a[aria-current="page"]')).toHaveLength(1);
    expect(document.querySelector('nav a.section-start')).toBeNull();
    for (const link of links) {
      expect(link.querySelectorAll('svg')).toHaveLength(1);
      expect(link.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
      expect(link.querySelector('svg')?.getAttribute('focusable')).toBe('false');
      expect(link.textContent.trim().length).toBeGreaterThan(0);
    }
    expect(document.querySelector('nav a[aria-current="page"]')?.getAttribute('href')).toBe(administrationNavigation.find((item): boolean => item.id === activeItem)?.href);
    expect(document.querySelector('.workspace-back')?.getAttribute('href')).toBe('/dashboard');
    expect(document.querySelector('.sidebar-navigation .brand')).toBeNull();
    expect(document.querySelector('.sidebar-navigation .account-block')).toBeNull();
    expect(document.querySelector('.brand')?.getAttribute('href')).toBe('/dashboard');
    expect(document.querySelector('h1')?.textContent).toBe('Existing admin page');
    expect(document.querySelector('.enter-forward')).toBeNull();
  });

  test('only the incoming sidebar animates across page-shell remounts', async (): Promise<void> => {
    const files = new URL('https://umbod.test/files');
    const admin = new URL('https://umbod.test/admin/connectors');
    const history = new WorkspaceNavigationHistory(files, true);
    const context = new Map([[workspaceNavigationHistoryKey, history]]);
    const children = createRawSnippet(() => ({ render: (): string => '<p>Existing page</p>' }));
    component = mount(WorkspaceShell, {
      target: document.body, context,
      props: { ...workspacePresentation, navigationItems: workspaceNavigation(true), activeItem: 'files', children }
    });
    history.startNavigation(files, admin, true);
    await tick();
    expect(document.querySelector('.enter-forward')).toBeNull();
    expect(document.querySelector('.enter-backward')).toBeNull();
    await unmount(component);
    component = mount(AdminShell, {
      target: document.body, context,
      props: { activeItem: 'connectors', accountIdentity: { kind: 'hidden' }, children }
    });
    await tick();
    history.completeNavigation(admin, true);
    expect(document.querySelector('.sidebar-navigation.enter-forward')).not.toBeNull();
    history.startNavigation(admin, files, true);
    await tick();
    expect(document.querySelector('.enter-forward')).toBeNull();
    expect(document.querySelector('.enter-backward')).toBeNull();
    await unmount(component);
    component = mount(WorkspaceShell, {
      target: document.body, context,
      props: { ...workspacePresentation, navigationItems: workspaceNavigation(true), activeItem: 'files', children }
    });
    await tick();
    history.completeNavigation(files, true);
    expect(document.querySelector('.sidebar-navigation.enter-backward')).not.toBeNull();
    history.startNavigation(files, admin, true);
    history.completeNavigation(admin, false);
    await tick();
    expect(document.querySelector('.enter-forward')).toBeNull();
    expect(document.querySelector('.enter-backward')).toBeNull();
  });

  test.each(['/files', '/connectors'])('root navigation remembers %s and applies motion only across sidebar contexts', async (destination: string): Promise<void> => {
    const dashboard = new URL('https://umbod.test/dashboard');
    const files = new URL(`https://umbod.test${destination}?sort=name#document`);
    const admin = new URL('https://umbod.test/admin/connectors');
    const groups = new URL('https://umbod.test/admin/groups');
    const history = new WorkspaceNavigationHistory(dashboard, true);
    component = mount(AdminShell, {
      target: document.body,
      context: new Map([[workspaceNavigationHistoryKey, history]]),
      props: {
        activeItem: 'connectors', accountIdentity: { kind: 'hidden' },
        children: createRawSnippet(() => ({ render: (): string => '<p>Existing page</p>' }))
      }
    });
    history.completeNavigation(files, true);
    history.startNavigation(files, admin, true);
    await tick();
    expect(document.querySelector('.workspace-back')?.getAttribute('href')).toBe(`${destination}?sort=name#document`);
    expect(document.querySelector('.sidebar-navigation.enter-forward')).not.toBeNull();
    expect(document.querySelector('.content-shell.enter-forward')).toBeNull();
    history.startNavigation(admin, groups, true);
    await tick();
    expect(document.querySelector('.enter-forward')).toBeNull();
    history.startNavigation(groups, files, true);
    await tick();
    expect(document.querySelector('.sidebar-navigation.enter-backward')).toBeNull();
    expect(document.querySelector('.workspace-back')?.getAttribute('href')).toBe(`${destination}?sort=name#document`);
  });
});
