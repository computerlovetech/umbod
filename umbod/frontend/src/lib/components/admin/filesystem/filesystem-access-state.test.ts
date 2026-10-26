import { describe, expect, it, vi } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import type { FilesystemAdministration } from '$lib/admin/filesystem/port';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { FilesystemAccessState } from './filesystem-access-state.svelte';

describe('filesystem editor state', () => {
  it('loads no hidden rows or defaults, manually edits exact values and saves', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue());
    expect(state.canSave).toBe(false);
    await state.load();
    expect(state.rows).toEqual([]);
    state.add();
    const id = state.rows[0].id;
    expect(state.rows[0]).toMatchObject({ issuer: '', group_id: '', permissions: [] });
    expect(state.canSave).toBe(false);
    state.edit(id, 'issuer', ' issuer ');
    state.edit(id, 'group_id', ' group ');
    state.toggle(id, 'write', true);
    expect(state.rows[0].permissions).toEqual(['write']);
    state.toggle(id, 'discover', true);
    expect(state.dirty).toBe(true);
    await state.save();
    expect(state.success).toBe('Filesystem access saved.');
    expect(state.saved?.groups[0]).toEqual({ issuer: ' issuer ', group_id: ' group ', permissions: ['write', 'discover'] });
    expect(state.dirty).toBe(false);
    state.toggle(state.rows[0].id, 'write', false);
    state.toggle(state.rows[0].id, 'write', true);
    expect(state.dirty).toBe(false);
  });
  it('loads legacy direct and recursive grants, permits repair and removal without locking unrelated rows', async () => {
    const unmanaged = [
      { issuer: '', group_id: 'recursive-blank-issuer', permissions: [] },
      { issuer: 'recursive-issuer', group_id: '', permissions: [] }
    ];
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({
      status: 'ready',
      groups: [
        { issuer: 'issuer', group_id: 'legacy-empty', permissions: [] },
        { issuer: '', group_id: 'legacy-blank-issuer', permissions: ['read'] },
        { issuer: 'issuer', group_id: ' ', permissions: ['read'] },
        { issuer: 'issuer', group_id: 'unrelated', permissions: ['discover'] }
      ],
      unmanaged_groups: unmanaged
    }));
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    await state.load();
    expect(state.error).toBe('');
    expect(state.editable).toBe(true);
    expect(state.dirty).toBe(false);
    expect(state.canSave).toBe(false);
    const [empty, blankIssuer, blankGroup, unrelated] = state.rows;
    state.toggle(unrelated.id, 'write', true);
    expect(state.rows.find((row) => row.id === unrelated.id)?.permissions).toEqual(['discover', 'write']);
    state.toggle(empty.id, 'read', true);
    state.edit(blankIssuer.id, 'issuer', 'repaired-issuer');
    state.remove(blankGroup.id);
    expect(state.canSave).toBe(true);
    await state.save();
    expect(state.saved?.groups).toEqual([
      { issuer: 'issuer', group_id: 'legacy-empty', permissions: ['read'] },
      { issuer: 'repaired-issuer', group_id: 'legacy-blank-issuer', permissions: ['read'] },
      { issuer: 'issuer', group_id: 'unrelated', permissions: ['discover', 'write'] }
    ]);
    expect(state.saved?.unmanaged_groups).toEqual(unmanaged);
    expect(state.dirty).toBe(false);
  });
  it('requires explicit confirmation for empty initialization and last grant revocation', async () => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy());
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    await state.load();
    await state.save();
    expect(state.confirmation).toBe('empty');
    expect((await api.getRootAccess()).status).toBe('uninitialized');
    state.cancelConfirmation();
    expect(state.saved?.status).toBe('uninitialized');
    await state.save();
    await state.confirm();
    expect(state.saved?.status).toBe('ready');
    state.add();
    state.edit(state.rows[0].id, 'issuer', 'issuer');
    state.edit(state.rows[0].id, 'group_id', 'group');
    state.toggle(state.rows[0].id, 'read', true);
    await state.save();
    state.remove(state.rows[0].id);
    expect((await api.getRootAccess()).groups).toHaveLength(1);
    await state.save();
    expect(state.confirmation).toBe('empty');
    await state.confirm();
    expect((await api.getRootAccess()).groups).toEqual([]);
  });
  it('prefills only the configured issuer and blocks unmanaged overlap', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ suggested_issuer: 'Configured Exact Issuer', unmanaged_groups: [{ issuer: 'Configured Exact Issuer', group_id: 'recursive', permissions: ['read'] }] })), new InMemoryGroupCatalogue());
    await state.load();
    state.add();
    expect(state.rows[0].issuer).toBe('Configured Exact Issuer');
    expect(state.rows[0].permissions).toEqual([]);
    state.edit(state.rows[0].id, 'group_id', 'recursive');
    state.toggle(state.rows[0].id, 'read', true);
    expect(state.canSave).toBe(false);
    expect(state.validationMessage).toContain('recursive');
  });
  it('preserves stale drafts without retry and explicitly discards on reload', async () => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ issuer: 'issuer', group_id: 'group', permissions: ['read'] }] }));
    const replace = vi.spyOn(api, 'replaceRootAccess');
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    await state.load();
    state.toggle(state.rows[0].id, 'write', true);
    await api.replaceRootAccess({ expected_revision: 'initial', groups: [] });
    replace.mockClear();
    await state.save();
    expect(replace).toHaveBeenCalledTimes(1);
    expect(state.rows[0].permissions).toEqual(['read', 'write']);
    expect(state.error).toContain('unsaved draft is preserved');
    expect(state.canSave).toBe(false);
    await state.save();
    expect(replace).toHaveBeenCalledTimes(1);
    state.requestReload();
    expect(state.confirmation).toBe('reload');
    state.cancelConfirmation();
    expect(state.dirty).toBe(true);
    state.requestReload();
    await state.confirm();
    expect(state.rows).toEqual([]);
    expect(state.dirty).toBe(false);
  });
  it('disables conflicts and reports safe failures', async () => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'conflict' }));
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    await state.load();
    state.add();
    expect(state.rows).toEqual([]);
    expect(state.canSave).toBe(false);
    const failed = new FilesystemAccessState({ getRootAccess: async () => { throw new HttpError(500, '', { secret: 'raw failure' }); }, replaceRootAccess: api.replaceRootAccess }, new InMemoryGroupCatalogue());
    await failed.load();
    expect(failed.error).not.toContain('raw failure');
    expect(failed.error).toContain('Reload');
  });
  it('exposes pending load and save states and ignores results after disposal', async () => {
    const api = new InMemoryFilesystemAdministration(rootPolicy());
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    const loading = state.load();
    expect(state.loading).toBe(true);
    await loading;
    await state.save();
    const saving = state.confirm();
    expect(state.saving).toBe(true);
    expect(state.editable).toBe(false);
    await saving;
    const disposed = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    const pending = disposed.load();
    disposed.dispose();
    await pending;
    expect(disposed.saved).toBe(null);
  });
});
