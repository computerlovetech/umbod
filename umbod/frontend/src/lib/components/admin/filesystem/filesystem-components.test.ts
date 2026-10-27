import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import FilesystemAccessEditor from './FilesystemAccessEditor.svelte';
import GroupRegistrationDialog from '../group-permissions/shared/GroupRegistrationDialog.svelte';
import { GroupRegistrationState } from '../group-permissions/shared/group-registration-state.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';

describe('filesystem accessible presentation', () => {
  it('shows five inline controls and one save without issuer inputs or legacy disclosures', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'operators', permissions: ['read', 'share'] }] })), new InMemoryGroupCatalogue([{ group_id: 'operators' }, { group_id: 'zero-access' }]));
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    for (const label of ['operators', 'zero-access', 'Add Group', 'Browse root', 'Read', 'Create items', 'Delete', 'Share', 'Save permissions']) expect(body).toContain(label);
    expect(body.match(/type="checkbox"/g)).toHaveLength(5);
    expect(body.match(/ checked/g)).toHaveLength(2);
    expect(body.match(/<button[^>]*aria-label="Save permissions"/g)).toHaveLength(1);
    expect(body).not.toContain('<dialog');
    expect(body).not.toMatch(/<input(?![^>]*type="checkbox")/);
    for (const text of ['issuer', 'Group claim', 'Advanced access details', 'Repair legacy', 'Recursive grants', 'Read-only']) expect(body).not.toContain(text);
    expect(body).toContain('aria-current="true"');
    expect(body).toContain('Other access rules remain unchanged');
  });
  it('shows blocked IDs absent from the catalogue without unusable permission actions', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', blocked_group_ids: ['blocked-group'] })), new InMemoryGroupCatalogue());
    await state.load();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('blocked-group');
    expect(body).toContain('managed outside this editor');
    expect(body).not.toContain('type="checkbox"');
    expect(body).not.toContain('Save permissions');
    expect(body).not.toContain('issuer');
  });
  it('keeps saving editable drafts reachable while a blocked group is selected', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', blocked_group_ids: ['blocked-group'] })), new InMemoryGroupCatalogue([{ group_id: 'blocked-group' }]));
    await state.load();
    state.setGroupPermissions('editable', ['read']);
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('managed outside this editor');
    expect(body).not.toContain('type="checkbox"');
    expect(body).toContain('Save permissions');
    expect(state.canSave).toBe(true);
    await state.save();
    expect(state.saved?.groups).toEqual([{ group_id: 'editable', permissions: ['read'] }]);
  });
  it('retains the independent group registration dialog', (): void => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue());
    const registration = new GroupRegistrationState(state.registerGroup, (): void => {});
    registration.show();
    const { body } = render(GroupRegistrationDialog, { props: { registration } });
    for (const label of ['Group ID', 'Register group', 'Cancel', 'saved immediately and independently of permission changes', 'grants no access']) expect(body).toContain(label);
    expect(body).not.toContain('issuer');
    expect(body).not.toContain('type="checkbox"');
  });
  it('confirms only clearing configurable permissions during empty setup', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue());
    await state.load();
    expect(render(FilesystemAccessEditor, { props: { state } }).body).toContain('Save to finish setup.');
    await state.save();
    const { body } = render(FilesystemAccessEditor, { props: { state } });
    expect(body).toContain('Clear configurable group permissions?');
    expect(body).toContain('Clear group permissions');
    expect(body).toContain('Configurable group permissions will be cleared. Other access rules remain unchanged.');
    expect(body).not.toContain('All direct root group grants');
  });
  it('shows creation guidance only when Browse root is unchecked', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue([{ group_id: 'creators' }]));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    const guidance = 'Also select Browse root to allow creation.';
    expect(render(FilesystemAccessEditor, { props: { state } }).body).not.toContain(guidance);
    editor.toggle('write', true);
    expect(render(FilesystemAccessEditor, { props: { state } }).body).toContain(guidance);
    editor.toggle('discover', true);
    expect(render(FilesystemAccessEditor, { props: { state } }).body).not.toContain(guidance);
  });
});
