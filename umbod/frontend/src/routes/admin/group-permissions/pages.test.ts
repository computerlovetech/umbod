import { render } from 'svelte/server';
import { Window } from 'happy-dom';
import { describe, expect, test, vi } from 'vitest';
import ConnectorsPage from './connectors/+page.svelte';
import FilesystemPage from './filesystem/+page.svelte';
import type { GroupPermissionsPageData } from '$lib/admin/group-permissions';

vi.mock('$app/state', () => ({
  navigating: { to: null, from: null },
  page: { url: new URL('https://umbod.test/admin/group-permissions/connectors') }
}));
vi.mock('$lib/components/feedback', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

const data: GroupPermissionsPageData = {
  status: 'ready', groups: [], preloadedGroup: null, assignableTargets: [],
  exactMatchGuidance: '', initialTarget: null, originHref: null
};

describe('group permissions pages', () => {
  test.each(['connectors', 'filesystem'] as const)('renders the %s tab within the shared administration section', (activeTab): void => {
    const body = activeTab === 'connectors'
      ? render(ConnectorsPage, { props: { data } }).body
      : render(FilesystemPage, { props: { data: { accountIdentity: { kind: 'hidden' } } } }).body;
    const document = new Window().document;
    document.body.innerHTML = body;
    expect([...document.querySelectorAll('h1')].map((heading) => heading.textContent)).toEqual(['Group permissions']);
    const navigation = document.querySelector('nav[aria-label="Group permission type"]');
    expect(navigation).not.toBeNull();
    expect([...navigation!.querySelectorAll('a')].map((link) => ({
      label: link.textContent, href: link.getAttribute('href'), current: link.getAttribute('aria-current')
    }))).toEqual([
      { label: 'Connectors', href: '/admin/group-permissions/connectors', current: activeTab === 'connectors' ? 'page' : null },
      { label: 'Filesystem', href: '/admin/group-permissions/filesystem', current: activeTab === 'filesystem' ? 'page' : null }
    ]);
    const sidebar = document.querySelector('nav[aria-label="Workspace navigation"]');
    expect([...sidebar!.querySelectorAll('a[aria-current="page"]')].map((link) => link.textContent)).toEqual(['Group permissions']);
    expect(sidebar!.querySelector('a[href="/admin/group-permissions/connectors"]')).not.toBeNull();
    expect(sidebar!.querySelector('a[href="/admin/filesystem"]')).toBeNull();
  });
});
