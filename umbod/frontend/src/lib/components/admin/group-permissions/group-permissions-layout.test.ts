import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { describe, expect, it } from 'vitest';
import GroupPermissionsPage from './GroupPermissionsPage.svelte';
import GroupPermissionsGroupHeader from './GroupPermissionsGroupHeader.svelte';

describe('shared group permissions presentation', () => {
  it.each(['connectors', 'filesystem'] as const)('renders the %s page with the shared heading and navigation', (activeTab): void => {
    const children = createRawSnippet(() => ({ render: (): string => '<p>Permission editor content</p>' }));
    const body = render(GroupPermissionsPage, { props: { activeTab, description: 'Assign group access.', children } }).body;
    expect(body).toContain('aria-labelledby="group-permissions-title"');
    expect(body).toContain('Assign group access.');
    expect(body).toContain('Manage groups');
    expect(body).toContain('Permission editor content');
    expect(body).toMatch(new RegExp('href="/admin/group-permissions/' + activeTab + '"[^>]*aria-current="page"'));
    expect(body).not.toContain('Back to OpenAPI connector');
  });

  it('preserves the optional connector return link', (): void => {
    const children = createRawSnippet(() => ({ render: (): string => '<p>Editor</p>' }));
    const body = render(GroupPermissionsPage, { props: { activeTab: 'connectors', description: 'Assign access.', backHref: '/admin/openapi-connectors/server', children } }).body;
    expect(body).toContain('href="/admin/openapi-connectors/server"');
    expect(body).toContain('Back to OpenAPI connector');
  });

  it('renders group metadata with an optional scope badge', (): void => {
    const badge = createRawSnippet(() => ({ render: (): string => '<span>Root only</span>' }));
    const body = render(GroupPermissionsGroupHeader, { props: { groupId: 'provider-team', label: 'Support Team', description: 'Shared group description', badge } }).body;
    expect(body).toContain('Support Team');
    expect(body).toContain('Shared group description');
    expect(body).toContain('provider-team');
    expect(body).toContain('Root only');
    expect(body).toMatch(/aria-hidden="true"[^>]*>ST/);
  });

  it('omits missing group descriptions and scope badges', (): void => {
    const body = render(GroupPermissionsGroupHeader, { props: { groupId: 'team', label: 'Team', description: '' } }).body;
    expect(body.match(/<p[ >]/g)).toHaveLength(1);
    expect(body).not.toContain('Root only');
  });
});
