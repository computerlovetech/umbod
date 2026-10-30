import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { Window } from 'happy-dom';
import { describe, expect, test, vi } from 'vitest';
import PermissionsLayout from './+layout.svelte';

const state = vi.hoisted(() => ({ page: { url: new URL('https://umbod.test/admin/group-permissions/connectors') } }));
vi.mock('$app/state', () => ({ navigating: { to: null, from: null }, page: state.page }));
vi.mock('$app/navigation', () => ({ afterNavigate: vi.fn() }));
vi.mock('$lib/admin/infrastructure/admin-api', () => ({ adminApi: (): object => ({ groups: {}, filesystem: {} }) }));

describe('persistent group permissions layout', () => {
  test.each(['connectors', 'filesystem'] as const)('owns the shared chrome for the %s tab', (activeTab): void => {
    state.page.url = new URL('https://umbod.test/admin/group-permissions/' + activeTab);
    const children = createRawSnippet(() => ({ render: (): string => '<p>Active permission editor</p>' }));
    const body = render(PermissionsLayout, { props: { data: { permissionGroups: [], accountIdentity: { kind: 'hidden' } }, children } }).body;
    const document = new Window().document;
    document.body.innerHTML = body;
    expect([...document.querySelectorAll('h1')].map((heading) => heading.textContent)).toEqual(['Group permissions']);
    expect(body).not.toContain('admin-eyebrow');
    const navigation = document.querySelector('nav[aria-label="Group permission type"]')!;
    expect([...navigation.querySelectorAll('a')].map((link) => ({
      label: link.textContent, href: link.getAttribute('href'), current: link.getAttribute('aria-current')
    }))).toEqual([
      { label: 'Connectors', href: '/admin/group-permissions/connectors', current: activeTab === 'connectors' ? 'page' : null },
      { label: 'Filesystem', href: '/admin/group-permissions/filesystem', current: activeTab === 'filesystem' ? 'page' : null }
    ]);
    const sidebar = document.querySelector('nav[aria-label="Workspace navigation"]')!;
    expect([...sidebar.querySelectorAll('a[aria-current="page"]')].map((link) => link.textContent)).toEqual(['Group permissions']);
    expect(body).toContain('Active permission editor');
    expect(document.querySelectorAll('aside[aria-label="Groups"]')).toHaveLength(1);
  });
});
