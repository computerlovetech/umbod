import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
import AdminShell from '../AdminShell.svelte';
import { workspaceNavigation } from '$lib/workspace/navigation';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));
describe('filesystem accessible presentation', () => {
  it('shows initialization, exact fields, five unchecked permissions and staged removal', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()));
    await state.load();
    expect(render(FilesystemAccessEditor, { props: { state } }).body).toContain('Not set up');
    state.add();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    for (const label of ['Filesystem access', 'Identity issuer', 'Exact group ID', 'Browse root', 'Create items', 'Read', 'Delete', 'Share', 'Add group', 'Remove group', 'Unsaved changes', 'Discard changes']) expect(body).toContain(label);
    expect(body.match(/type="checkbox"/g)).toHaveLength(5);
    expect(body).not.toContain(' checked');
    expect(body).toContain('for="issuer-0"');
    expect(body).toContain('for="group-0"');
    expect(body).toContain('no inheritance');
    expect(body).toContain('verified authentication');
  });
  it('shows the explicit empty-policy confirmation and read-only unmanaged grants', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ unmanaged_groups: [{ issuer: 'issuer', group_id: 'recursive', permissions: ['read'] }] })));
    await state.load();
    await state.save();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('<dialog');
    expect(body).toContain('aria-labelledby="filesystem-confirmation-title"');
    expect(body).toContain('data-dialog-cancel');
    expect(body).toContain('Save empty policy');
    expect(body).toContain('User grants and recursive grants stay unchanged');
    expect(body).toContain('Recursive grants');
    expect(body).toContain('Read-only');
  });
  it('renders editable legacy rows and labels empty recursive identities and permissions', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({
      status: 'ready',
      groups: [
        { issuer: 'issuer', group_id: 'empty-direct', permissions: [] },
        { issuer: '', group_id: 'blank-direct-issuer', permissions: ['read'] },
        { issuer: 'issuer', group_id: '', permissions: ['read'] }
      ],
      unmanaged_groups: [
        { issuer: '', group_id: 'empty-recursive', permissions: [] },
        { issuer: 'issuer', group_id: '', permissions: [] }
      ]
    })));
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('value="empty-direct"');
    expect(body).toContain('value="blank-direct-issuer"');
    expect(body).toContain('Blank issuer (legacy)');
    expect(body).toContain('Blank group ID (legacy)');
    expect(body).toContain('No permissions');
    expect(body.match(/Remove group/g)).toHaveLength(3);
    expect(body).not.toContain('<fieldset disabled');
    expect(body).toContain('select at least one permission');
  });
  it('keeps setup details collapsed and presents a focused empty state', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()));
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('No groups selected');
    expect(body).toContain('Root only');
    expect(body).toContain('Access details');
    expect(body).toContain('Save to finish setup.');
    expect(body.match(/<details[^>]*>/g)?.every((details) => !details.includes(' open'))).toBe(true);
    expect(body).not.toContain('No CLI setup is required');
    expect(body).not.toContain('Permissions are never selected automatically');
    expect(body).not.toContain('Removing a row stages revocation');
    expect(body).not.toContain('No unsaved changes');
  });
  it('shows creation guidance only when the browse permission is missing', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()));
    await state.load();
    state.add();
    const row = state.rows[0];
    const guidance = 'Also select Browse root to allow creation.';
    expect(render(FilesystemAccessEditor, { props: { state } }).body).not.toContain(guidance);
    state.toggle(row.id, 'write', true);
    expect(render(FilesystemAccessEditor, { props: { state } }).body).toContain(guidance);
    expect(state.rows[0].permissions).toEqual(['write']);
    state.toggle(row.id, 'discover', true);
    expect(render(FilesystemAccessEditor, { props: { state } }).body).not.toContain(guidance);
  });
  it('links admin navigation and marks the filesystem item active', () => {
    expect(workspaceNavigation(false).some((item) => item.id === 'filesystem')).toBe(false);
    const { body } = render(AdminShell, { props: { activeItem: 'filesystem', accountIdentity: { kind: 'hidden' }, children: createRawSnippet(() => ({ render: (): string => '<p>Editor</p>' })) } });
    expect(body).toMatch(/href="\/admin\/filesystem"[^>]*aria-current="page"/);
    expect(body).toContain('Filesystem</a>');
  });
});
