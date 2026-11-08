import { afterEach, describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { NodeAccess, SharingRecipient, SharingRecipientSearchResult } from '../domain/sharing';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { FilesState } from './files-state.svelte';
import { SharingDialogState } from './sharing-dialog-state.svelte';
import { SharingEligibilityState } from './sharing-eligibility-state.svelte';

afterEach((): void => { vi.restoreAllMocks(); vi.useRealTimers(); });

const recipients: SharingRecipient[] = [
  { type: 'group', group_id: ' Team A ', label: 'Friendly team' },
  { type: 'group', group_id: 'team-b', label: 'Team B' },
  { type: 'user', user_id: 'person-a', label: 'Hidden person' },
  { type: 'user', user_id: 'person-b', label: 'New person' }
];
const access: NodeAccess = { node_id: fileId, revision: 'hash-1', grants: [{ recipient: { type: 'group', group_id: ' Team A ', label: 'Friendly team' }, permissions: ['write', 'share'] }, { recipient: { type: 'user', user_id: 'person-a', label: 'Hidden person' }, permissions: ['read'] }], blocked_recipients: [{ type: 'group', group_id: 'blocked' }, { type: 'user', user_id: 'protected-person' }] };

function fixture(): { api: InMemoryFilesApi; state: SharingDialogState; revoke: ReturnType<typeof vi.fn>; recheck: ReturnType<typeof vi.fn> } {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  api.sharing.configure(access, recipients);
  const revoke = vi.fn();
  const recheck = vi.fn();
  return { api, state: new SharingDialogState(api.sharing, revoke, recheck), revoke, recheck };
}

describe('sharing eligibility', (): void => {
  test('resolves renamed home labels by ID for buttons, dialog and saved announcement without renaming nodes', async (): Promise<void> => {
    const { api } = fixture();
    const home = filesystemNode({ id: folderId, parent_id: rootId, name: 'Renamed home' });
    api.sharing.configure({ ...access, node_id: home.id }, recipients);
    const eligibility = new SharingEligibilityState(api.sharing, (node): string => node.id === folderId ? 'Files' : node.name || 'Shared files');
    try {
      expect(eligibility.label(home)).toBe('Files');
      expect(eligibility.label(filesystemFixture[2])).toBe('Notes.txt');
      await eligibility.dialog.show(home);
      expect(eligibility.dialog.nodeName).toBe('Files');
      expect(eligibility.dialog.node?.name).toBe('Renamed home');
      await eligibility.dialog.save();
      expect(eligibility.dialog.status).toBe('Sharing updated for “Files”.');
      expect(home.name).toBe('Renamed home');
    } finally {
      eligibility.dispose();
    }
  });

  test('starts hidden, accepts only validated inspection, and never assumes administrator or node-kind authority', async (): Promise<void> => {
    const { api } = fixture();
    const eligibility = new SharingEligibilityState(api.sharing);
    const response = deferred<NodeAccess>();
    vi.spyOn(api.sharing, 'inspectAccess').mockReturnValueOnce(response.promise);
    eligibility.select([filesystemFixture[2]]);
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
    expect(inspect.mock.calls[0][2]?.aborted).toBe(true);
    eligibility.reset();
    for (const [, recipientType, signal] of inspect.mock.calls) {
      expect(recipientType).toBe('group');
      expect(signal?.aborted).toBe(true);
    }
    response.resolve(access);
    await Promise.resolve();
    await Promise.resolve();
    expect(inspect).toHaveBeenCalledTimes(4);
    for (const node of nodes) expect(eligibility.available(node.id)).toBe(false);
    eligibility.dispose();
  });

  test('fails closed on browse failure and checks newly created unseeded rows', async (): Promise<void> => {
    const { api } = fixture();
    api.sharing.configure({ ...access, node_id: folderId }, recipients);
    vi.spyOn(api.filesystem, 'listChildren').mockRejectedValueOnce(new Error('listing failed'));
    const files = new FilesState(api);
    await files.load(folderId);
    expect(files.sharing.available(folderId)).toBe(false);
    expect(files.phase).toBe('error');
    await files.load(folderId);
    const target = files.creationTarget()!;
    const created = await api.filesystem.createFolder(folderId, { name: 'New', metadata: { content_type: {}, attributes: {} } });
    api.sharing.configure({ ...access, node_id: created.id }, recipients);
    await files.acceptCreated(folderId, target.generation, created);
    await vi.waitFor(() => expect(files.sharing.available(created.id)).toBe(true));
    files.dispose();
  });
});

describe('sharing dialog state', (): void => {
  test('projects matching custom options and clears search after adding an exact group ID', async (): Promise<void> => {
    const { api, state } = fixture();
    api.sharing.configure(access, [...recipients, { type: 'group', group_id: 'blocked', label: 'Hidden' }]);
    await state.show(filesystemFixture[2]);
    state.remove(' Team A ');
    state.changeFilter('FRIENDLY');
    await state.search.refresh();
    expect(state.recipientOptions).toEqual([{ value: ' Team A ', label: 'Friendly team ( Team A )' }]);
    state.changeFilter(' TEAM A ');
    await state.search.refresh();
    expect(state.recipientOptions[0].value).toBe(' Team A ');
    state.add(' Team A ');
    expect(state.filter).toBe('');
    expect(state.recipients[0].id).toBe(' Team A ');
    expect(state.recipientOptions).toEqual([]);
    state.changeFilter('unregistered');
    await state.search.refresh();
    expect(state.recipientOptions).toEqual([]);
  });

  test('freshly inspects each opening, preserves existing permissions, defaults only new groups and saves exact replacements', async (): Promise<void> => {
    const { api, state, revoke, recheck } = fixture();
    const inspect = vi.spyOn(api.sharing, 'inspectAccess');
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await state.show(filesystemFixture[2]);
    expect(inspect.mock.calls[0]).toEqual([fileId, 'group', expect.any(AbortSignal)]);
    expect(state.recipients).toEqual([{ recipient: access.grants[0].recipient, id: ' Team A ', permissions: access.grants[0].permissions, label: 'Friendly team' }]);
    expect(state.canSave).toBe(true);
    state.changeFilter('Team B');
    await state.search.refresh();
    state.add('team-b');
    expect(state.recipients[1].permissions).toEqual(['discover', 'read']);
    state.changePermission('team-b', 'delete', true);
    state.remove(' Team A ');
    await state.save();
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'hash-1', { grants: [{ recipient: { type: 'group', group_id: 'team-b' }, permissions: ['discover', 'read', 'delete'] }] }, 'group');
    expect(state.open).toBe(false);
    expect(state.status).toContain('Notes.txt');
    expect(revoke).toHaveBeenCalledWith(fileId);
    expect(recheck).toHaveBeenCalledWith(fileId);
    await state.show(filesystemFixture[2]);
    expect(inspect.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(state.recipients[0].permissions).toEqual(['discover', 'read', 'delete']);
    state.remove('team-b');
    await state.save();
    expect(replace.mock.calls[1][2]).toEqual({ grants: [] });
    expect(replace.mock.calls.every((call) => call[3] === 'group')).toBe(true);
    expect((await api.sharing.inspectAccess(fileId, 'user')).grants).toEqual([access.grants[1]]);
  });

  test('requires a nonempty permission set and excludes blocked groups while allowing existing entries to be removed', async (): Promise<void> => {
    const { api, state } = fixture();
    api.sharing.configure(access, [...recipients, { type: 'group', group_id: 'blocked', label: 'Hidden' }]);
    await state.show(filesystemFixture[2]);
    state.add('blocked');
    expect(state.recipients).toHaveLength(1);
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
    state.changeFilter('Team B');
    await state.search.refresh();
    state.add('team-b');
    expect(state.open).toBe(true);
    expect(state.pending).toBe(true);
    await state.selectRecipientType('user');
    expect(state.recipientType).toBe('group');
    expect(state.recipients).toHaveLength(1);
    expect(replace).toHaveBeenCalledOnce();
    response.resolve(access);
    await saving;
    expect(state.open).toBe(false);
  });

  test('412 keeps draft and disables blind resubmission until explicit authoritative reload', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    state.changeFilter('Team B');
    await state.search.refresh();
    state.add('team-b');
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(new HttpError(412, 'Conflict', {}));
    await state.save();
    expect(state.recipients).toHaveLength(2);
    expect(state.needsReload).toBe(true);
    expect(state.error).toContain('discard this draft');
    await state.save();
    expect(replace).toHaveBeenCalledOnce();
    await state.reloadLatest();
    expect(state.recipients).toHaveLength(1);
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

  test.each([new AuthenticationRequiredError(), new HttpError(401, 'Unauthorized', {})])('search authentication failure stops editing: %s', async (error): Promise<void> => {
    const { api, state, revoke } = fixture();
    await state.show(filesystemFixture[2]);
    vi.spyOn(api.sharing, 'searchRecipients').mockRejectedValueOnce(error);
    state.changeFilter('Team');
    await state.search.refresh();
    expect(state.phase).toBe('sign-in');
    expect(state.canSave).toBe(false);
    expect(revoke).toHaveBeenCalledWith(fileId);
    state.dispose();
  });

  test('search denial rechecks node authority before revoking sharing eligibility', async (): Promise<void> => {
    const { api, state, revoke } = fixture();
    await state.show(filesystemFixture[2]);
    vi.spyOn(api.sharing, 'searchRecipients').mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    vi.spyOn(api.sharing, 'inspectAccess').mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    state.changeFilter('Team');
    await state.search.refresh();
    expect(state.phase).toBe('denied');
    expect(state.canSave).toBe(false);
    expect(revoke).toHaveBeenCalledWith(fileId);
    state.dispose();
  });

  test('directory denial blocks that scope without revoking authorized group sharing', async (): Promise<void> => {
    const { api, state, revoke } = fixture();
    await state.show(filesystemFixture[2]);
    await state.selectRecipientType('user');
    vi.spyOn(api.sharing, 'searchRecipients').mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    state.changeFilter('Person');
    await state.search.refresh();
    expect(state.phase).toBe('ready');
    expect(state.search.unavailable).toBe(true);
    expect(state.canSave).toBe(false);
    expect(revoke).not.toHaveBeenCalled();
    await state.selectRecipientType('group');
    expect(state.canSave).toBe(true);
    expect(state.search.unavailable).toBe(false);
    state.dispose();
  });

  test('422 preserves the draft and requires authoritative reload before further editing', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    state.changeFilter('Team B');
    await state.search.refresh();
    state.add('team-b');
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(new HttpError(422, 'Invalid recipient', {}));
    await state.save();
    expect(state.recipients).toHaveLength(2);
    expect(state.needsReload).toBe(true);
    expect(state.canSave).toBe(false);
    state.remove('team-b');
    await state.save();
    expect(state.recipients).toHaveLength(2);
    expect(replace).toHaveBeenCalledOnce();
    await state.reloadLatest();
    expect(state.recipients).toHaveLength(1);
    expect(state.canSave).toBe(true);
  });

  test.each([new NetworkError(new Error('lost response')), new Error('malformed JSON')])('uncertain mutation %s requires explicit inspection', async (error): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    state.changeFilter('Team B');
    await state.search.refresh();
    state.add('team-b');
    const replace = vi.spyOn(api.sharing, 'replaceAccess').mockRejectedValueOnce(error);
    await state.save();
    await state.save();
    expect(replace).toHaveBeenCalledOnce();
    expect(state.recipients).toHaveLength(2);
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

  test('searches, adds, edits and removes users while saving only user access', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    await state.selectRecipientType('user');
    expect(state.recipients.map((entry) => entry.id)).toEqual(['person-a']);
    state.changeFilter('New person');
    await state.search.refresh();
    expect(state.recipientOptions).toEqual([{ value: 'person-b', label: 'New person (person-b)' }]);
    state.add('person-b');
    state.changePermission('person-b', 'share', true);
    state.remove('person-a');
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await state.save();
    expect(replace).toHaveBeenCalledExactlyOnceWith(fileId, 'hash-1', { grants: [{ recipient: { type: 'user', user_id: 'person-b' }, permissions: ['discover', 'read', 'share'] }] }, 'user');
    expect((await api.sharing.inspectAccess(fileId, 'group')).grants).toEqual([access.grants[0]]);
  });

  test('clean switches inspect a fresh revision and dirty switches require an explicit decision', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    api.sharing.configure({ ...access, revision: 'latest' }, recipients);
    const inspect = vi.spyOn(api.sharing, 'inspectAccess');
    await state.selectRecipientType('user');
    expect(inspect).toHaveBeenCalledWith(fileId, 'user', expect.any(AbortSignal));
    state.changePermission('person-a', 'write', true);
    await state.selectRecipientType('group');
    expect(state.confirmingSwitch).toBe(true);
    expect(state.recipientType).toBe('user');
    expect(state.canSave).toBe(false);
    state.keepEditing();
    expect(state.recipients[0].permissions).toEqual(['read', 'write']);
    const replace = vi.spyOn(api.sharing, 'replaceAccess');
    await state.save();
    expect(replace.mock.calls[0][1]).toBe('latest');
    await state.show(filesystemFixture[2]);
    state.remove(' Team A ');
    await state.selectRecipientType('user');
    await state.discardAndSwitch();
    expect(state.recipientType).toBe('user');
    expect(state.dirty).toBe(false);
    expect(state.recipients[0].permissions).toEqual(['read', 'write']);
  });

  test.each(['query', 'scope', 'close'] as const)('ignores stale search results after changing %s', async (change): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    const response = deferred<SharingRecipientSearchResult>();
    const search = vi.spyOn(api.sharing, 'searchRecipients').mockReturnValueOnce(response.promise);
    state.changeFilter('Team');
    const searching = state.search.refresh();
    if (change === 'query') {
      state.changeFilter('missing');
      await state.search.refresh();
    } else if (change === 'scope') await state.selectRecipientType('user');
    else await state.close();
    expect(search.mock.calls[0][3]?.aborted).toBe(true);
    response.resolve({ recipients: [recipients[1]], has_more: true });
    await searching;
    expect(state.recipientOptions).toEqual([]);
    expect(state.search.hasMore).toBe(false);
    expect(state.search.loading).toBe(false);
    if (change === 'query') expect(state.filter).toBe('missing');
    if (change === 'scope') expect(state.recipientType).toBe('user');
    if (change === 'close') expect(state.open).toBe(false);
  });

  test('search failure leaves loaded grants editable and saveable', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.show(filesystemFixture[2]);
    vi.spyOn(api.sharing, 'searchRecipients').mockRejectedValueOnce(new Error('offline'));
    state.changeFilter('Team');
    await state.search.refresh();
    expect(state.search.error).not.toBe('');
    expect(state.editable).toBe(true);
    state.changePermission(' Team A ', 'read', true);
    await state.save();
    expect(state.open).toBe(false);
    expect((await api.sharing.inspectAccess(fileId, 'group')).grants[0].permissions).toEqual(['write', 'share', 'read']);
  });

  test('debounces searches and never requests blank input', async (): Promise<void> => {
    vi.useFakeTimers();
    const { api, state } = fixture();
    const search = vi.spyOn(api.sharing, 'searchRecipients');
    await state.show(filesystemFixture[2]);
    expect(state.search.emptyMessage).toBe('Type a name to search');
    state.changeFilter('  ');
    await state.search.refresh();
    await vi.advanceTimersByTimeAsync(250);
    expect(search).not.toHaveBeenCalled();
    state.changeFilter('Friendly');
    await vi.advanceTimersByTimeAsync(249);
    expect(search).not.toHaveBeenCalled();
    state.changeFilter('Team B');
    await vi.advanceTimersByTimeAsync(250);
    expect(search).toHaveBeenCalledExactlyOnceWith(fileId, 'Team B', 'group', expect.any(AbortSignal));
    expect(state.recipientOptions[0].value).toBe('team-b');
    state.dispose();
  });

  test('self-revocation hides action until a new inspection confirms authority', async (): Promise<void> => {
    const { api } = fixture();
    const eligibility = new SharingEligibilityState(api.sharing);
    eligibility.select([filesystemFixture[2]]);
    await vi.waitFor(() => expect(eligibility.available(fileId)).toBe(true));
    await eligibility.dialog.show(filesystemFixture[2]);
    vi.spyOn(api.sharing, 'replaceAccess').mockImplementationOnce(async (): Promise<NodeAccess> => { api.sharing.revoke(fileId); return { ...access, revision: 'revoked', grants: [] }; });
    eligibility.dialog.remove(' Team A ');
    await eligibility.dialog.save();
    await vi.waitFor(() => expect(eligibility.available(fileId)).toBe(false));
    expect(eligibility.dialog.status).toContain('Sharing updated');
  });
});
