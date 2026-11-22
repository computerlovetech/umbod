import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { Window } from 'happy-dom';
import { describe, expect, test, vi } from 'vitest';
import PermissionsLayout from './+layout.svelte';

const state = vi.hoisted(() => ({ page: { url: new URL('https://umbod.test/admin/group-permissions/connectors') } }));
vi.mock('$app/state', () => ({ navigating: { to: null, from: null }, page: state.page }));
vi.mock('$app/navigation', () => ({ afterNavigate: vi.fn() }));
vi.mock('#lib/admin/infrastructure/admin-api.js', () => ({ adminApi: (): object => ({ groups: {}, namespaces: {} }) }));

describe('persistent group permissions layout', () => {
  test('selects the requested registered group on entry', (): void => {
    state.page.url = new URL('https://umbod.test/admin/group-permissions/connectors?group=research%20team');
    const children = createRawSnippet(() => ({ render: (): string => '<p>Editor</p>' }));
    const permissionGroups = [
      { group_id: 'admin', label: 'Administrators', description: '', revision: 1 },
      { group_id: 'research team', label: 'Research team', description: '', revision: 1 }
    ];
    const document = new Window().document;
    document.body.innerHTML = render(PermissionsLayout, { props: { data: { permissionGroups, accountIdentity: { kind: 'hidden' } }, children } }).body;
    expect(document.querySelector('.group-header h2')?.textContent).toBe('Research team');
  });

  test.each(['connectors', 'filesystem'] as const)('owns the shared chrome for the %s tab', (activeTab): void => {
    state.page.url = new URL('https://umbod.test/admin/group-permissions/' + activeTab);
    const children = createRawSnippet(() => ({ render: (): string => '<p>Active permission editor</p>' }));
    const permissionGroups = [{ group_id: 'admin', label: 'Administrators', description: '', revision: 1 }];
    const body = render(PermissionsLayout, { props: { data: { permissionGroups, accountIdentity: { kind: 'hidden' } }, children } }).body;
    const document = new Window().document;
    document.body.innerHTML = body;
    expect([...document.querySelectorAll('h1')].map((heading) => heading.textContent)).toEqual(['Permissions']);
    expect(body).not.toContain('admin-eyebrow');
    expect(body).not.toContain('Add namespace');
    const navigation = document.querySelector('nav[aria-label="Group permission type"]')!;
    expect([...navigation.querySelectorAll('a')].map((link) => ({
      label: link.textContent, href: link.getAttribute('href'), current: link.getAttribute('aria-current')
    }))).toEqual([
      { label: 'Connectors', href: '/admin/group-permissions/connectors', current: activeTab === 'connectors' ? 'page' : null },
      { label: 'Filesystem', href: '/admin/group-permissions/filesystem', current: activeTab === 'filesystem' ? 'page' : null }
    ]);
    const sidebar = document.querySelector('nav[aria-label="Administration navigation"]')!;
    expect([...sidebar.querySelectorAll('a[aria-current="page"]')].map((link) => link.getAttribute('href'))).toEqual(['/admin/group-permissions/connectors']);
    expect(body).toContain('Active permission editor');
    expect(document.querySelector('.page-header .admin-lede')?.textContent).toBe('Choose a group to manage connector permissions and shared namespace access.');
    expect(document.querySelectorAll('aside[aria-label="Groups"]')).toHaveLength(1);
    expect(document.querySelector('aside[aria-label="Groups"]')?.textContent).toContain('Administrators');
  });
});
