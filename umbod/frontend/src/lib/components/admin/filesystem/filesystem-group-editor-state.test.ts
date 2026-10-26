import { describe, expect, it, vi } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import type { FilesystemAdministration } from '$lib/admin/filesystem/port';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';

const groups = [
  { issuer: 'issuer', group_id: 'readers', permissions: ['read'] as const },
  { issuer: 'issuer', group_id: 'creators', permissions: ['write'] as const }
].map((group) => ({ ...group, permissions: [...group.permissions] }));

describe('filesystem group modal state', () => {
  it.each([false, true])('cancels an add draft without changing rows or dirty state when dirty is %s', async (dirty: boolean): Promise<void> => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups, suggested_issuer: 'configured-issuer' }));
    const state = new FilesystemAccessState(api);
    await state.load();
    if (dirty) state.edit(state.rows[0].id, 'group_id', 'changed-readers');
    const rows = state.groups;
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openAdd();
    expect(editor.draft).toEqual({ issuer: 'configured-issuer', group_id: '', permissions: [] });
    editor.edit('group_id', 'new-group');
    editor.toggle('read', true);
    expect(state.groups).toEqual(rows);
    expect(state.dirty).toBe(dirty);
    editor.cancel();
    expect(editor.draft).toBeNull();
    expect(editor.editingId).toBeNull();
    expect(state.groups).toEqual(rows);
    expect(state.dirty).toBe(dirty);
    expect((await api.getRootAccess()).groups).toEqual(groups);
  });

  it('cancels an edit draft without changing the selected row or its permissions', async (): Promise<void> => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups }));
    const state = new FilesystemAccessState(api);
    await state.load();
    const rows = state.groups;
    const editor = new FilesystemGroupEditorState(() => state);
    editor.select(state.rows[1].id);
    editor.openEdit();
    expect(editor.draft).toEqual(rows[1]);
    editor.edit('issuer', 'changed-issuer');
    editor.edit('group_id', 'changed-group');
    editor.toggle('write', false);
    editor.toggle('share', true);
    expect(state.groups).toEqual(rows);
    editor.cancel();
    expect(editor.draft).toBeNull();
    expect(editor.editingId).toBeNull();
    expect(editor.selected).toEqual(state.rows[1]);
    expect(state.groups).toEqual(rows);
    expect(state.dirty).toBe(false);
    expect((await api.getRootAccess()).groups).toEqual(rows);
  });

  it('applies an added row and selects it without persisting the policy', async (): Promise<void> => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups }));
    const replace = vi.spyOn(api, 'replaceRootAccess');
    const state = new FilesystemAccessState(api);
    await state.load();
    const saved = state.saved;
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openAdd();
    editor.edit('issuer', ' exact issuer ');
    editor.edit('group_id', ' exact group ');
    editor.toggle('read', true);
    editor.apply();
    expect(state.rows).toHaveLength(3);
    expect(editor.selected).toEqual(state.rows[2]);
    expect(editor.selectedId).toBe(state.rows[2].id);
    expect(editor.selected).toMatchObject({ issuer: ' exact issuer ', group_id: ' exact group ', permissions: ['read'] });
    expect(editor.draft).toBeNull();
    expect(state.dirty).toBe(true);
    expect(state.canSave).toBe(true);
    expect(state.saved).toBe(saved);
    expect(replace).not.toHaveBeenCalled();
    expect((await api.getRootAccess()).groups).toEqual(groups);
  });

  it('applies an edit in place and keeps the updated row selected without persistence', async (): Promise<void> => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups }));
    const replace = vi.spyOn(api, 'replaceRootAccess');
    const state = new FilesystemAccessState(api);
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    const id = state.rows[1].id;
    editor.select(id);
    editor.openEdit();
    expect(editor.validationMessage).toBe('');
    editor.edit('group_id', 'updated-creators');
    editor.toggle('discover', true);
    editor.apply();
    expect(state.rows).toHaveLength(2);
    expect(state.groups[0]).toEqual(groups[0]);
    expect(editor.selectedId).toBe(id);
    expect(editor.selected).toEqual({ id, issuer: 'issuer', group_id: 'updated-creators', permissions: ['write', 'discover'] });
    expect(editor.draft).toBeNull();
    expect(editor.editingId).toBeNull();
    expect(state.dirty).toBe(true);
    expect(replace).not.toHaveBeenCalled();
    expect((await api.getRootAccess()).groups).toEqual(groups);
  });

  it.each(['direct', 'recursive'] as const)('rejects a duplicate %s issuer and group pair when adding or editing', async (kind): Promise<void> => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({
      status: 'ready', groups,
      unmanaged_groups: kind === 'recursive' ? [{ issuer: 'issuer', group_id: 'recursive', permissions: ['share'] }] : []
    }));
    const state = new FilesystemAccessState(api);
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    const duplicateId = kind === 'direct' ? 'readers' : 'recursive';
    for (const editing of [false, true]) {
      if (editing) { editor.select(state.rows[1].id); editor.openEdit(); }
      else editor.openAdd();
      editor.edit('issuer', 'issuer');
      editor.edit('group_id', duplicateId);
      editor.toggle('read', true);
      expect(editor.validationMessage).toBe('This issuer and group ID already have a grant.');
      editor.apply();
      expect(editor.draft).not.toBeNull();
      expect(state.groups).toEqual(groups);
      expect(state.dirty).toBe(false);
      editor.edit('issuer', 'different-issuer');
      expect(editor.validationMessage).toBe('');
      editor.cancel();
    }
    expect((await api.getRootAccess()).groups).toEqual(groups);
  });

  it('requires nonblank identity fields and at least one permission before applying', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()));
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    editor.openAdd();
    for (const [issuer, groupId, checked] of [['', 'group', true], ['issuer', ' ', true], ['issuer', 'group', false]] as const) {
      editor.edit('issuer', issuer);
      editor.edit('group_id', groupId);
      editor.toggle('read', checked);
      expect(editor.validationMessage).toContain('select at least one permission');
      editor.apply();
      expect(state.rows).toEqual([]);
      expect(state.dirty).toBe(false);
      expect(editor.draft).not.toBeNull();
    }
  });

  it('falls back to the first available row after removing the selection or reloading', async (): Promise<void> => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups }));
    const state = new FilesystemAccessState(api);
    await state.load();
    const editor = new FilesystemGroupEditorState(() => state);
    expect(editor.selected).toEqual(state.rows[0]);
    editor.select(state.rows[1].id);
    expect(editor.selected).toEqual(state.rows[1]);
    state.remove(state.rows[1].id);
    expect(editor.selected).toEqual(state.rows[0]);
    state.remove(state.rows[0].id);
    expect(editor.selected).toBeNull();
    await state.load();
    expect(editor.selected).toEqual(state.rows[0]);
    editor.select(state.rows[1].id);
    const previousId = editor.selectedId;
    await state.load();
    expect(state.rows.some((row) => row.id === previousId)).toBe(false);
    expect(editor.selected).toEqual(state.rows[0]);
    expect(state.dirty).toBe(false);
  });
});
