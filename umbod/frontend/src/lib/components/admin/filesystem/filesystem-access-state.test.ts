import { describe, expect, it, vi } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { FilesystemAccessState } from './filesystem-access-state.svelte';

describe('filesystem editor state', () => {
  it('requires confirmation for empty setup and clearing the final grant', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy());
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    expect(state.canSave).toBe(false);
    await state.load();
    await state.save();
    expect(state.confirmation).toBe('empty');
    expect((await api.getRootAccess()).status).toBe('uninitialized');
    state.cancelConfirmation();
    await state.save();
    await state.confirm();
    expect(state.saved?.status).toBe('ready');
    state.setGroupPermissions(' exact group ', ['read']);
    await state.save();
    expect(state.saved?.groups).toEqual([{ group_id: ' exact group ', permissions: ['read'] }]);
    expect(state.dirty).toBe(false);
    state.setGroupPermissions(' exact group ', []);
    await state.save();
    expect((await api.getRootAccess()).groups).toHaveLength(1);
    expect(state.confirmation).toBe('empty');
    await state.confirm();
    expect((await api.getRootAccess()).groups).toEqual([]);
  });
  it('preserves stale drafts without retry and explicitly discards on reload', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'group', permissions: ['read'] }] }));
    const replace = vi.spyOn(api, 'replaceRootAccess');
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    await state.load();
    state.setGroupPermissions('group', ['read', 'write']);
    await api.replaceRootAccess({ expected_revision: 'initial', groups: [] });
    replace.mockClear();
    await state.save();
    expect(replace).toHaveBeenCalledTimes(1);
    expect(state.groups[0].permissions).toEqual(['read', 'write']);
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
  it('blocks conflicts and blocked IDs without locking unrelated groups', async (): Promise<void> => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ blocked_group_ids: ['blocked'] })), new InMemoryGroupCatalogue());
    await state.load();
    expect(state.groupEntries.map((group) => group.group_id)).toEqual(['blocked']);
    state.setGroupPermissions('blocked', ['read']);
    expect(state.groups).toEqual([]);
    state.setGroupPermissions('other', ['read']);
    expect(state.canSave).toBe(true);
    const conflict = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy({ status: 'conflict' })), new InMemoryGroupCatalogue());
    await conflict.load();
    conflict.setGroupPermissions('other', ['read']);
    expect(conflict.groups).toEqual([]);
    expect(conflict.canSave).toBe(false);
  });
  it.each(['filesystem_policy_storage_failure', 'filesystem_policy_unavailable'])('reports safe %s failures', async (code): Promise<void> => {
    const state = new FilesystemAccessState({
      getRootAccess: async () => { throw new HttpError(503, '', { detail: { code }, secret: 'raw failure' }); },
      replaceRootAccess: async () => rootPolicy()
    }, new InMemoryGroupCatalogue());
    await state.load();
    expect(state.error).not.toContain('raw failure');
    expect(state.error.toLowerCase()).toContain('reload');
  });
  it('exposes pending states and ignores results after disposal', async (): Promise<void> => {
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
