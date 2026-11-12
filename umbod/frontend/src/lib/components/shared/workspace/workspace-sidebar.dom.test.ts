import { afterEach, describe, expect, test, vi } from 'vitest';
import { createRawSnippet, mount, tick, unmount } from 'svelte';
import { administrationNavigation, workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
import { WorkspaceNavigationHistory } from '$lib/workspace/navigation-history.svelte';
import { workspaceNavigationHistoryKey } from '$lib/workspace/navigation-history-context';
import AdminShell from '$lib/components/admin/AdminShell.svelte';
import WorkspaceShell from './WorkspaceShell.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

describe('contextual sidebar rendering', (): void => {
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
      ? ['Dashboard', 'Connectors', 'Files', 'Getting started', 'Administration']
      : ['Dashboard', 'Connectors', 'Files', 'Getting started']);
    for (const link of links) {
      expect(link.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
      expect(link.querySelector('svg')?.getAttribute('focusable')).toBe('false');
    }
    expect(document.querySelector('nav a[aria-current="page"]')?.getAttribute('href')).toBe('/files');
    expect(document.querySelector('a.section-start')?.getAttribute('href')).toBe(allowed ? '/admin/connectors' : undefined);
    expect(document.querySelector('.workspace-back')).toBeNull();
    expect(document.querySelector('h1')?.textContent).toBe('Existing files page');
  });

  test.each(['connectors', 'groups', 'groupPermissions', 'analytics', 'instanceConfiguration'] as const)('administration selects %s while preserving the page and identity frame', async (activeItem): Promise<void> => {
    component = mount(AdminShell, {
      target: document.body,
      props: {
        activeItem, accountIdentity: { kind: 'hidden' },
        children: createRawSnippet(() => ({ render: (): string => '<h1>Existing admin page</h1>' }))
      }
    });
    await tick();
    const links = Array.from(document.querySelectorAll('nav[aria-label="Administration navigation"] a'));
    expect(links.map((link): string | null => link.getAttribute('href'))).toEqual(administrationNavigation.map((item): string => item.href));
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
