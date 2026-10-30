import { describe, expect, it } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';

describe('inline filesystem group permissions', () => {
  it('projects catalogue labels and descriptions without changing permission identities', async (): Promise<void> => {
    const catalogue = new InMemoryGroupCatalogue([{ group_id: ' claim / value ', label: 'Report owners', description: 'Own reports', revision: 4 }]);
    const access = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), catalogue);
    await access.load();
    expect(access.groupEntries[0]).toMatchObject({ id: ' claim / value ', group_id: ' claim / value ', label: 'Report owners', description: 'Own reports', permissions: [] });
  });

  it('stages multiple groups across selections and persists the whole projection', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'readers', permissions: ['read'] }] }));
    const access = new FilesystemAccessState(api, new InMemoryGroupCatalogue([{ group_id: 'readers', label: 'readers', description: '', revision: 1 }, { group_id: ' exact creators ', label: 'exact creators', description: '', revision: 1 }]));
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.toggle('share', true);
    editor.select(' exact creators ');
    editor.toggle('write', true);
    editor.select('readers');
    expect(editor.permissions).toEqual(['read', 'share']);
    expect((await api.getRootAccess()).groups).toEqual([{ group_id: 'readers', permissions: ['read'] }]);
    await access.save();
    expect((await api.getRootAccess()).groups).toEqual([
      { group_id: 'readers', permissions: ['read', 'share'] },
      { group_id: ' exact creators ', permissions: ['write'] }
    ]);
    expect(access.dirty).toBe(false);
    editor.select(' exact creators ');
    editor.toggle('write', false);
    expect(editor.selected?.group_id).toBe(' exact creators ');
    expect(editor.permissions).toEqual([]);
    await access.save();
    await access.load();
    expect(editor.selected?.group_id).toBe(' exact creators ');
    expect(editor.permissions).toEqual([]);
  });
  it('keeps saved unregistered groups selected until clearing is saved or discarded', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'unregistered', permissions: ['read'] }] }));
    const access = new FilesystemAccessState(api, new InMemoryGroupCatalogue([{ group_id: 'other', label: 'other', description: '', revision: 1 }]));
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.select('unregistered');
    editor.toggle('read', false);
    expect(editor.selected?.group_id).toBe('unregistered');
    expect(editor.permissions).toEqual([]);
    editor.toggle('share', true);
    expect(access.groups).toEqual([{ group_id: 'unregistered', permissions: ['share'] }]);
    access.requestReload();
    await access.confirm();
    expect(editor.permissions).toEqual(['read']);
    editor.toggle('read', false);
    await access.save();
    expect(access.confirmation).toBe('empty');
    await access.confirm();
    expect((await api.getRootAccess()).groups).toEqual([]);
    expect(access.groupEntries.map((group) => group.group_id)).toEqual(['other']);
  });
  it('disables blocked assignment while allowing other group edits', async (): Promise<void> => {
    const access = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ blocked_group_ids: ['blocked'] })), new InMemoryGroupCatalogue([{ group_id: 'other', label: 'other', description: '', revision: 1 }]));
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.select('blocked');
    expect(editor.editable).toBe(false);
    expect(editor.assignmentMessage).toContain('managed outside this editor');
    editor.toggle('read', true);
    expect(access.groups).toEqual([]);
    editor.select('other');
    expect(editor.editable).toBe(true);
    editor.toggle('read', true);
    expect(access.groups).toEqual([{ group_id: 'other', permissions: ['read'] }]);
  });
});
