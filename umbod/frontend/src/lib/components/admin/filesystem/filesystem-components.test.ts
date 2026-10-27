import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
import FilesystemGroupDialog from './FilesystemGroupDialog.svelte';
import GroupRegistrationDialog from '../group-permissions/shared/GroupRegistrationDialog.svelte';
import { GroupRegistrationState } from '../group-permissions/shared/group-registration-state.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
import AdminShell from '../AdminShell.svelte';
import { workspaceNavigation } from '$lib/workspace/navigation';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

describe('filesystem accessible presentation', () => {
  it('shows all catalogue groups including zero-access groups and separates registration from assignment', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready' })), new InMemoryGroupCatalogue([{ group_id: 'empty-group' }, { group_id: 'connector-only' }]));
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    for (const label of ['empty-group', 'connector-only', 'No direct root access', 'Registration alone grants no access', 'Add Group', 'Assign filesystem permissions', 'Save policy']) expect(body).toContain(label);
    expect(body).toContain('aria-current="true"');
    expect(body).not.toContain('<input');
    expect(body).not.toContain('Remove filesystem access');
    expect(body).not.toContain('Unsaved changes');
  });

  it('shows independent issuer grants with clearly scoped access removal', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [
      { issuer: 'first-issuer', group_id: 'operators', permissions: ['read'] },
      { issuer: 'second-issuer', group_id: 'operators', permissions: ['write'] }
    ] })), new InMemoryGroupCatalogue([{ group_id: 'operators' }]));
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    for (const label of ['Group identity', 'Identity issuer', 'first-issuer', 'second-issuer', 'operators', 'Browse root', 'Create items', 'Read', 'Delete', 'Share', 'Edit filesystem permissions', 'Remove filesystem access', 'Allowed', 'No access']) expect(body).toContain(label);
    expect(body).not.toContain('Remove group');
    expect(body).toContain('no inheritance');
    expect(body).toContain('verified authentication');
    for (const row of state.rows) state.remove(row.id);
    const removed = render(FilesystemAccessEditor, { props: { state } }).body;
    expect(removed).toContain('operators');
    expect(removed).toContain('No direct root access');
    expect(removed).toContain('Unsaved changes');
    expect(removed).toContain('Discard changes');
  });

  it('registers a group using only an exact ID with independent persistence guidance', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue());
    const registration = new GroupRegistrationState(state.registerGroup, (): void => {});
    registration.show();
    const { body } = render(GroupRegistrationDialog, { props: { registration } });
    for (const label of ['Add group', 'Group ID', 'Exact group ID', 'Register group', 'Cancel', 'saved immediately and independently of permission changes', 'grants no access', 'group claim value', 'does not create IdP membership']) expect(body).toContain(label);
    expect(body).not.toContain('Identity issuer');
    expect(body).not.toContain('type="checkbox"');
    expect(body).toContain('data-dialog-cancel');
    expect(body).toMatch(/<button[^>]*type="submit"[^>]*disabled/);
  });

  it('assigns permissions with an immutable selected identity, editable issuer and unchecked permissions', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ suggested_issuer: 'configured-issuer' })), new InMemoryGroupCatalogue([{ group_id: 'selected group' }]));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openAdd();
    const { body } = render(FilesystemGroupDialog, { props: { editor } });
    for (const label of ['Assign filesystem permissions', 'Group ID', 'Identity issuer', 'Browse root', 'Create items', 'Read', 'Delete', 'Share', 'Cancel', 'Stage permissions']) expect(body).toContain(label);
    expect(body).toContain('aria-labelledby="filesystem-group-title"');
    expect(body).toContain('aria-describedby="filesystem-group-description"');
    expect(body).toMatch(/id="filesystem-group-id"[^>]*value="selected group"[^>]*readonly/);
    expect(body).toContain('value="configured-issuer"');
    expect(body).toContain('Changes apply only after Save policy.');
    expect(body.match(/type="checkbox"/g)).toHaveLength(5);
    expect(body).not.toContain(' checked');
    expect(body).toMatch(/<button[^>]*type="submit"[^>]*disabled/);
  });

  it('edits the selected grant without retyping group identity', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ issuer: 'issuer', group_id: 'operators', permissions: ['read', 'share'] }] })), new InMemoryGroupCatalogue([{ group_id: 'operators' }]));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openEdit(state.rows[0].id);
    const { body } = render(FilesystemGroupDialog, { props: { editor } });
    expect(body).toContain('Edit filesystem permissions');
    expect(body).toContain('value="operators" readonly');
    expect(body).toContain('value="issuer"');
    expect(body.match(/ checked/g)).toHaveLength(2);
    expect(body).not.toMatch(/<button[^>]*type="submit"[^>]*disabled/);
  });

  it('distinguishes recursive-only groups from groups without direct root grants', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ unmanaged_groups: [{ issuer: 'issuer', group_id: 'recursive', permissions: ['read'] }] })), new InMemoryGroupCatalogue([{ group_id: 'recursive' }]));
    await state.load();
    const body = render(FilesystemAccessEditor, { props: { state } }).body;
    expect(body).toContain('No direct root access');
    expect(body).toContain('This group has recursive grants');
    expect(body).not.toContain('No filesystem access');
    expect(state.groupEntries.map((group) => group.group_id)).toEqual(['recursive']);
  });

  it('shows explicit empty-policy confirmation and read-only recursive grants', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ unmanaged_groups: [{ issuer: 'issuer', group_id: 'recursive', permissions: ['read'] }] })), new InMemoryGroupCatalogue());
    await state.load();
    await state.save();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('aria-labelledby="filesystem-confirmation-title"');
    expect(body).toContain('Save empty policy');
    expect(body).toContain('User grants and recursive grants stay unchanged');
    expect(body).toContain('Recursive grants');
    expect(body).toContain('Read-only');
  });

  it.each([
    { issuer: 'issuer', group_id: 'empty-direct', permissions: [] },
    { issuer: '', group_id: 'blank-direct-issuer', permissions: ['read'] },
    { issuer: 'issuer', group_id: '', permissions: ['read'] }
  ] as const)('keeps malformed legacy identity $group_id inspectable and removable', async (group): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ ...group, permissions: [...group.permissions] }], unmanaged_groups: [{ issuer: '', group_id: '', permissions: [] }] })), new InMemoryGroupCatalogue());
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body.match(/<h2[^>]*>([^<]*)<\/h2>/)?.[1]).toBe(group.group_id || 'Blank group ID (legacy)');
    expect(body).toContain('Legacy filesystem grant');
    expect(body).toContain('Edit filesystem permissions');
    expect(body).toContain('Remove filesystem access');
    expect(body).toContain('Blank issuer (legacy)');
    expect(body).toContain('Blank group ID (legacy)');
    expect(body).toContain('No permissions');
    expect(body).toContain('select at least one permission');
  });

  it('keeps setup details collapsed with a focused empty state', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue());
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('No groups selected');
    expect(body).toContain('Register a group, then assign root access separately.');
    expect(body).toContain('Save to finish setup.');
    expect(body.match(/<details[^>]*>/g)?.every((details) => !details.includes(' open'))).toBe(true);
  });

  it('shows browse guidance only when creation is selected without discover', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue([{ group_id: 'creators' }]));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openAdd();
    editor.edit('issuer', 'issuer');
    const guidance = 'Also select Browse root to allow creation.';
    expect(render(FilesystemGroupDialog, { props: { editor } }).body).not.toContain(guidance);
    editor.toggle('write', true);
    expect(render(FilesystemGroupDialog, { props: { editor } }).body).toContain(guidance);
    editor.apply();
    expect(render(FilesystemAccessEditor, { props: { state } }).body).toContain(guidance);
    editor.openEdit(state.rows[0].id);
    editor.toggle('discover', true);
    editor.apply();
    expect(render(FilesystemAccessEditor, { props: { state } }).body).not.toContain(guidance);
  });

  it('uses group permissions navigation without a standalone filesystem item', (): void => {
    for (const allowed of [false, true]) expect(workspaceNavigation(allowed).some((item) => item.id === 'filesystem')).toBe(false);
    const { body } = render(AdminShell, { props: { activeItem: 'groupPermissions', accountIdentity: { kind: 'hidden' }, children: createRawSnippet(() => ({ render: (): string => '<p>Editor</p>' })) } });
    expect(body).toMatch(/href="\/admin\/group-permissions\/connectors"[^>]*aria-current="page"/);
    expect(body).toContain('Group permissions</a>');
    expect(body).not.toContain('href="/admin/filesystem"');
  });
});
