import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
import FilesystemGroupDialog from './FilesystemGroupDialog.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
import AdminShell from '../AdminShell.svelte';
import { workspaceNavigation } from '$lib/workspace/navigation';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));
describe('filesystem accessible presentation', () => {
  it('shows a selected group overview without inline editing controls', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({
      status: 'ready', groups: [{ issuer: 'exact-issuer', group_id: 'operators', permissions: ['read'] }]
    })));
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    for (const label of ['Filesystem access', 'Group identity', 'Identity issuer', 'exact-issuer', 'operators', 'Browse root', 'Create items', 'Read', 'Delete', 'Share', 'Add Group', 'Edit group', 'Remove group', 'Allowed', 'No access']) expect(body).toContain(label);
    expect(body).toContain('aria-current="true"');
    expect(body).not.toContain('<input');
    expect(body).not.toContain('Unsaved changes');
    expect(body).toContain('no inheritance');
    expect(body).toContain('verified authentication');
    state.remove(state.rows[0].id);
    const removed = render(FilesystemAccessEditor, { props: { state } }).body;
    expect(removed).toContain('Unsaved changes');
    expect(removed).toContain('Discard changes');
  });
  it('presents exact identity fields and five unchecked permissions in the add modal', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ suggested_issuer: 'configured-issuer' })));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openAdd();
    const { body } = render(FilesystemGroupDialog, { props: { editor } });
    for (const label of ['Add group', 'Group ID', 'Identity issuer', 'Exact group ID', 'Browse root', 'Create items', 'Read', 'Delete', 'Share', 'Cancel']) expect(body).toContain(label);
    expect(body).toContain('aria-labelledby="filesystem-group-title"');
    expect(body).toContain('aria-describedby="filesystem-group-description"');
    expect(body).toContain('for="filesystem-group-id"');
    expect(body).toContain('for="filesystem-group-issuer"');
    expect(body).toContain('value="configured-issuer"');
    expect(body).toContain('data-dialog-cancel');
    expect(body).toContain('Changes apply only after saving the policy.');
    expect(body.match(/type="checkbox"/g)).toHaveLength(5);
    expect(body).not.toContain(' checked');
    expect(body).toMatch(/<button[^>]*type="submit"[^>]*disabled/);
  });
  it('presents the selected identity and checked permissions in the edit modal', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({
      status: 'ready', groups: [{ issuer: 'issuer', group_id: 'operators', permissions: ['read', 'share'] }]
    })));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openEdit();
    const { body } = render(FilesystemGroupDialog, { props: { editor } });
    expect(body).toContain('Edit group');
    expect(body).toContain('Apply changes');
    expect(body).toContain('value="operators"');
    expect(body).toContain('value="issuer"');
    expect(body.match(/ checked/g)).toHaveLength(2);
    expect(body).not.toMatch(/<button[^>]*type="submit"[^>]*disabled/);
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
  it.each([
    { issuer: 'issuer', group_id: 'empty-direct', permissions: [] },
    { issuer: '', group_id: 'blank-direct-issuer', permissions: ['read'] },
    { issuer: 'issuer', group_id: '', permissions: ['read'] }
  ] as const)('shows the selected legacy identity $group_id in the overview', async (group): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({
      status: 'ready',
      groups: [{ ...group, permissions: [...group.permissions] }],
      unmanaged_groups: [
        { issuer: '', group_id: 'empty-recursive', permissions: [] },
        { issuer: 'issuer', group_id: '', permissions: [] }
      ]
    })));
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body.match(/<h2[^>]*>([^<]*)<\/h2>/)?.[1]).toBe(group.group_id || 'Blank group ID (legacy)');
    expect(body.match(/<dd[^>]*>([^<]*)<\/dd>/g)?.[1]).toContain(`>${group.issuer || 'Blank issuer (legacy)'}</dd>`);
    expect(body).toContain('aria-current="true"');
    expect(body).not.toContain('<input');
    expect(body).toContain('Edit group');
    expect(body).toContain('Blank issuer (legacy)');
    expect(body).toContain('Blank group ID (legacy)');
    expect(body).toContain('No permissions');
    expect(body.match(/aria-label="Remove group"/g)).toHaveLength(1);
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
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openAdd();
    editor.edit('issuer', 'issuer');
    editor.edit('group_id', 'creators');
    const guidance = 'Also select Browse root to allow creation.';
    expect(render(FilesystemGroupDialog, { props: { editor } }).body).not.toContain(guidance);
    editor.toggle('write', true);
    expect(render(FilesystemGroupDialog, { props: { editor } }).body).toContain(guidance);
    editor.apply();
    expect(render(FilesystemAccessEditor, { props: { state } }).body).toContain(guidance);
    expect(state.rows[0].permissions).toEqual(['write']);
    editor.openEdit();
    editor.toggle('discover', true);
    expect(render(FilesystemGroupDialog, { props: { editor } }).body).not.toContain(guidance);
    editor.apply();
    expect(render(FilesystemAccessEditor, { props: { state } }).body).not.toContain(guidance);
  });
  it('uses group permissions navigation without a standalone filesystem item', () => {
    for (const allowed of [false, true]) expect(workspaceNavigation(allowed).some((item) => item.id === 'filesystem')).toBe(false);
    const { body } = render(AdminShell, { props: { activeItem: 'groupPermissions', accountIdentity: { kind: 'hidden' }, children: createRawSnippet(() => ({ render: (): string => '<p>Editor</p>' })) } });
    expect(body).toMatch(/href="\/admin\/group-permissions\/connectors"[^>]*aria-current="page"/);
    expect(body).toContain('Group permissions</a>');
    expect(body).not.toContain('href="/admin/filesystem"');
  });
});
