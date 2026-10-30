import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { NodeAccess, SharingGroup } from '../domain/sharing';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { FilesState } from './files-state.svelte';
import { SharingDialogState } from './sharing-dialog-state.svelte';
import { SharingEligibilityState } from './sharing-eligibility-state.svelte';

const groups: SharingGroup[] = [
  { group_id: ' Team A ', label: 'Friendly team', description: 'Design people' },
  { group_id: 'team-b', label: 'Team B', description: 'Other people' }
];
const access: NodeAccess = { node_id: fileId, revision: 'hash-1', groups: [{ group_id: ' Team A ', permissions: ['write', 'share'] }], blocked_group_ids: ['blocked'] };

function fixture(): { api: InMemoryFilesApi; state: SharingDialogState; revoke: ReturnType<typeof vi.fn>; recheck: ReturnType<typeof vi.fn> } {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  api.sharing.configure(access, groups);
  const revoke = vi.fn();
  const recheck = vi.fn();
  return { api, state: new SharingDialogState(api.sharing, revoke, recheck), revoke, recheck };
}

describe('sharing eligibility', (): void => {
  test('starts hidden, accepts only validated inspection, and never assumes administrator or node-kind authority', async (): Promise<void> => {
    const { api } = fixture();
    const eligibility = new SharingEligibilityState(api.sharing);
    const response = deferred<NodeAccess>();
    vi.spyOn(api.sharing, 'inspectAccess').mockReturnValueOnce(response.promise);
    eligibility.selectCurrent(filesystemFixture[2]);
    expect(eligibility.available(fileId)).toBe(false);
    response.resolve(access);
    await vi.waitFor(() => expect(eligibility.available(fileId)).toBe(true));
    eligibility.select([filesystemFixture[0], filesystemFixture[1]]);
    await Promise.resolve();
    expect(eligibility.available(rootId)).toBe(false);
    expect(eligibility.available(folderId)).toBe(false);
  });

  test('bounds row probes, fences stale navigation, and aborts removed nodes', async (): Promise<void> => {
    const { api } = fixture();
    const eligibility = new SharingEligibilityState(api.sharing);
    const response = deferred<NodeAccess>();
    const inspect = vi.spyOn(api.sharing, 'inspectAccess').mockImplementation(async (id): Promise<NodeAccess> => ({ ...await response.promise, node_id: id }));
    const nodes = Array.from({ length: 9 }, (_, i) => filesystemNode({ id: `00000000-0000-4000-8000-${String(i + 10).padStart(12, '0')}` }));
    eligibility.select(nodes);
    expect(inspect).toHaveBeenCalledTimes(4);
    eligibility.remove(nodes[0].id);
    expect(inspect.mock.calls[0][1]?.aborted).toBe(true);
    eligibility.reset();
    for (const [, signal] of inspect.mock.calls) expect(signal?.aborted).toBe(true);
    response.resolve(access);
    await Promise.resolve();
    await Promise.resolve();
    expect(inspect).toHaveBeenCalledTimes(4);
    for (const node of nodes) expect(eligibility.available(node.id)).toBe(false);
    eligibility.dispose();
  });

  test('checks current directory independently of failed listing and starts newly created rows', async (): Promise<void> => {
    const { api } = fixture();
    api.sharing.configure({ ...access, node_id: folderId }, groups);
    vi.spyOn(api.filesystem, 'listChildren').mockRejectedValueOnce(new Error('listing failed'));
    const files = new FilesState(api);
    await files.load(folderId);
    await vi.waitFor(() => expect(files.sharing.available(folderId)).toBe(true));
    expect(files.phase).toBe('error');
    await files.load(folderId);
    const target = files.creationTarget()!;
    const created = await api.filesystem.createFolder(folderId, { name: 'New', metadata: { content_type: {}, attributes: {} } });
    api.sharing.configure({ ...access, node_id: created.id }, groups);
    await files.acceptCreated(folderId, target.generation, created);
    await vi.waitFor(() => expect(files.sharing.available(created.id)).toBe(true));
    files.dispose();
  });
});

describe('sharing dialog state', (): void => {
  test('projects matching custom options and clears search after adding an exact group ID', async (): Promise<void> => {
    const { api, state } = fixture();
    api.sharing.configure(access, [...groups, { group_id: 'blocked', label: 'Hidden', description: '' }]);
    await state.show(filesystemFixture[2]);
    state.remove(' Team A ');
    state.changeFilter('DESIGN');
    expect(state.groupOptions).toEqual([{ value: ' Team A ', label: 'Friendly team' }]);
    state.changeFilter(' TEAM A ');
    expect(state.groupOptions[0].value).toBe(' Team A ');
    state.add(' Team A ');
    expect(state.filter).toBe('');
    expect(state.groups[0].group_id).toBe(' Team A ');
    expect(state.groupOptions.map((option) => option.value)).toEqual(['team-b']);
    state.changeFilter('unregistered');
    expect(state.groupOptions).toEqual([]);
  });

  test('freshly inspects each opening, preserves existing permissions, defaults only new groups and saves exact replacements', async (): Promise<void> => {
    const { api, state, revoke, recheck } = fixture();
    const inspect = vi.spyOn(api.sharing, 'inspectAccess');
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await state.show(filesystemFixture[2]);
    expect(state.groups[0]).toEqual({ ...access.groups[0], label: 'Friendly team', description: 'Design people' });
    expect(state.canSave).toBe(true);
    state.add('team-b');
    expect(state.groups[1].permissions).toEqual(['discover', 'read']);
    state.changePermission('team-b', 'delete', true);
    state.remove(' Team A ');
    await state.save();
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'hash-1', { groups: [{ group_id: 'team-b', permissions: ['discover', 'read', 'delete'] }] });
    expect(state.open).toBe(false);
    expect(state.status).toContain('Notes.txt');
    expect(revoke).toHaveBeenCalledWith(fileId);
    expect(recheck).toHaveBeenCalledWith(fileId);
    await state.show(filesystemFixture[2]);
    expect(inspect.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(state.groups[0].permissions).toEqual(['discover', 'read', 'delete']);
    state.remove('team-b');
    await state.save();
    expect(replace.mock.calls[1][2]).toEqual({ groups: [] });
  });

  test('requires a nonempty permission set and excludes blocked groups while allowing existing entries to be removed', async (): Promise<void> => {
    const { api, state } = fixture();
    api.sharing.configure(access, [...groups, { group_id: 'blocked', label: 'Hidden', description: '' }]);
    await state.show(filesystemFixture[2]);
    state.add('blocked');
    expect(state.groups).toHaveLength(1);
    state.changePermission(' Team A ', 'write', false);
    state.changePermission(' Team A ', 'share', false);
    expect(state.canSave).toBe(false);
    state.remove(' Team A ');
    expect(state.canSave).toBe(true);
  });

  test('pending save blocks cancellation and duplicate mutation independent of form lifetime', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    const response = deferred<NodeAccess>();
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockReturnValueOnce(response.promise);
    const saving = state.save();
    await state.close();
    await state.save();
    state.add('team-b');
    expect(state.open).toBe(true);
    expect(state.pending).toBe(true);
    expect(state.groups).toHaveLength(1);
    expect(replace).toHaveBeenCalledOnce();
    response.resolve(access);
    await saving;
    expect(state.open).toBe(false);
  });

  test('412 keeps draft and disables blind resubmission until explicit authoritative reload', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    state.add('team-b');
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(new HttpError(412, 'Conflict', {}));
    await state.save();
    expect(state.groups).toHaveLength(2);
    expect(state.needsReload).toBe(true);
    expect(state.error).toContain('discard this draft');
    await state.save();
    expect(replace).toHaveBeenCalledOnce();
    await state.reloadLatest();
    expect(state.groups).toHaveLength(1);
    expect(state.canSave).toBe(true);
  });

  test.each([new AuthenticationRequiredError(), new HttpError(403, 'Forbidden', {})])('authority failure stops editing and revokes cached eligibility: %s', async (error): Promise<void> => {
    const { api, state, revoke } = fixture();
    await state.show(filesystemFixture[2]);
    vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(error);
    await state.save();
    expect(state.phase).toBe(error instanceof AuthenticationRequiredError ? 'sign-in' : 'denied');
    expect(state.editable).toBe(false);
    expect(revoke).toHaveBeenCalledWith(fileId);
  });

  test('422 keeps draft, refreshes eligible groups and requires unavailable recipients to be removed', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    state.add('team-b');
    vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(new HttpError(422, 'Invalid group', {}));
    await state.save();
    expect(state.groups).toHaveLength(2);
    expect(state.canSave).toBe(false);
    api.sharing.configure(access, [groups[0]]);
    await state.refreshGroups();
    expect(state.groups).toHaveLength(2);
    expect(state.canSave).toBe(false);
    state.remove('team-b');
    expect(state.canSave).toBe(true);
  });

  test.each([new NetworkError(new Error('lost response')), new Error('malformed JSON')])('uncertain mutation %s requires explicit inspection', async (error): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    state.add('team-b');
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(error);
    await state.save();
    await state.save();
    expect(replace).toHaveBeenCalledOnce();
    expect(state.groups).toHaveLength(2);
    expect(state.needsReload).toBe(true);
    await state.reloadLatest();
    expect(state.canSave).toBe(true);
  });

  test.each(['reset', 'dispose'] as const)('fences loading and mutation after %s', async (action): Promise<void> => {
    const first = fixture();
    const read = deferred<NodeAccess>();
    vi.spyOn(first.api.sharing, 'inspectAccess').mockReturnValueOnce(read.promise);
    const opening = first.state.show(filesystemFixture[2]);
    first.state[action]();
    read.resolve(access);
    await opening;
    expect(first.state.open).toBe(false);
    const second = fixture();
    await second.state.show(filesystemFixture[2]);
    const response = deferred<NodeAccess>();
    vi.spyOn(second.api.sharing, 'replaceAccess').mockReturnValueOnce(response.promise);
    const saving = second.state.save();
    second.state[action]();
    response.resolve(access);
    await saving;
    expect(second.state.open).toBe(false);
    expect(second.state.status).toBe('');
    expect(second.recheck).not.toHaveBeenCalled();
  });

  test.each(['conflict', 'invalid-recipient', 'catalogue-failure'] as const)('clears prior-node recovery after cancel and a new failed opening: %s', async (failure): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    state.changeFilter('prior node filter');
    if (failure === 'catalogue-failure') {
      vi.spyOn(api.sharing, 'listEligibleSharingGroups').mockRejectedValueOnce(new Error('offline'));
      await state.refreshGroups();
      expect(state.groupsError).not.toBe('');
    } else {
      vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(new HttpError(failure === 'conflict' ? 412 : 422, 'Rejected', {}));
      await state.save();
      expect(state.error).not.toBe('');
    }
    await state.close();
    api.sharing.configure({ ...access, node_id: folderId }, groups);
    const response = deferred<NodeAccess>();
    vi.spyOn(api.sharing, 'inspectAccess').mockReturnValueOnce(response.promise);
    const opening = state.show(filesystemFixture[1]);
    expect(state.phase).toBe('loading');
    expect(state.needsReload).toBe(false);
    expect(state.needsGroupsRefresh).toBe(false);
    expect(state.groupsError).toBe('');
    expect(state.error).toBe('');
    expect(state.filter).toBe('');
    expect(state.groups).toEqual([]);
    expect(state.availableGroups).toEqual([]);
    response.reject(new Error('new node unavailable'));
    await opening;
    expect(state.phase).toBe('error');
    expect(state.needsReload).toBe(false);
    expect(state.needsGroupsRefresh).toBe(false);
    expect(state.groupsError).toBe('');
    expect(state.error).not.toContain('kept');
    expect(state.availableGroups).toEqual([]);
  });

  test('self-revocation hides action until a new inspection confirms authority', async (): Promise<void> => {
    const { api } = fixture();
    const eligibility = new SharingEligibilityState(api.sharing);
    eligibility.selectCurrent(filesystemFixture[2]);
    await vi.waitFor(() => expect(eligibility.available(fileId)).toBe(true));
    await eligibility.dialog.show(filesystemFixture[2]);
    vi.spyOn(api.sharing, 'replaceAccess').mockImplementationOnce(async (): Promise<NodeAccess> => { api.sharing.revoke(fileId); return { ...access, revision: 'revoked', groups: [] }; });
    eligibility.dialog.remove(' Team A ');
    await eligibility.dialog.save();
    await vi.waitFor(() => expect(eligibility.available(fileId)).toBe(false));
    expect(eligibility.dialog.status).toContain('Sharing updated');
  });
});
