import { describe, expect, it } from 'vitest';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import type { GroupCatalogue } from '$lib/admin/groups/port';
import type { FilesystemAdministration } from '$lib/admin/filesystem/port';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import { GroupPermissionsApi } from '$lib/admin/group-permissions-api';
import type { Transport } from '$lib/admin/infrastructure/transport';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import { FilesystemGroupEditorState } from './filesystem-group-editor-state.svelte';
import { GroupRegistrationState } from '../group-permissions/shared/group-registration-state.svelte';

const noNetwork: Transport = { request: async (): Promise<never> => { throw new Error('Unexpected permission request'); } };

async function workspace(): Promise<{ access: FilesystemAccessState; editor: FilesystemGroupEditorState; catalogue: GroupCatalogue; filesystem: FilesystemAdministration }> {
  const catalogue: GroupCatalogue = new InMemoryGroupCatalogue([{ group_id: 'readers' }, { group_id: ' zero access ' }]);
  const filesystem: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', suggested_issuer: 'configured-issuer', groups: [{ issuer: 'issuer', group_id: 'readers', permissions: ['read'] }] }));
  const access = new FilesystemAccessState(filesystem, catalogue);
  await access.load();
  return { access, editor: new FilesystemGroupEditorState(() => access), catalogue, filesystem };
}

describe('shared catalogue and independent filesystem grants', () => {
  it('reuses connector registrations with zero filesystem access and preserves exact IDs', async (): Promise<void> => {
    const { access, editor, catalogue, filesystem } = await workspace();
    const connectors = new GroupPermissionsApi(noNetwork, catalogue);
    await connectors.permissions.register(' connector group ');
    await access.load();
    editor.select(' connector group ');
    expect(editor.selected).toMatchObject({ group_id: ' connector group ', registered: true, grants: [] });
    expect(access.dirty).toBe(false);
    expect((await filesystem.getRootAccess()).groups).toHaveLength(1);
    expect(await connectors.permissions.list()).toContainEqual({ groupId: ' zero access ' });
  });

  it('registers from filesystem immediately without policy grants and exposes the group to connectors', async (): Promise<void> => {
    const { access, editor, catalogue, filesystem } = await workspace();
    const registration = new GroupRegistrationState(access.registerGroup, editor.select);
    registration.show();
    registration.edit(' exact new group ');
    await registration.submit();
    expect(registration.open).toBe(false);
    expect(editor.selected).toMatchObject({ group_id: ' exact new group ', grants: [] });
    expect(access.dirty).toBe(false);
    expect(await new GroupPermissionsApi(noNetwork, catalogue).permissions.list()).toContainEqual({ groupId: ' exact new group ' });
    expect((await filesystem.getRootAccess()).groups).toHaveLength(1);
    await access.load();
    expect(access.catalogue).toContainEqual({ group_id: ' exact new group ' });
  });

  it('cancels registration and assignment without changing the catalogue or policy', async (): Promise<void> => {
    const { access, editor, catalogue, filesystem } = await workspace();
    const registration = new GroupRegistrationState(access.registerGroup, editor.select);
    registration.show();
    registration.edit('cancelled');
    registration.cancel();
    expect(await catalogue.list()).not.toContainEqual({ group_id: 'cancelled' });
    editor.select(' zero access ');
    editor.openAdd();
    expect(editor.draft).toEqual({ issuer: 'configured-issuer', group_id: ' zero access ', permissions: [] });
    editor.edit('group_id', 'must not change');
    expect(editor.draft?.group_id).toBe(' zero access ');
    editor.toggle('read', true);
    editor.cancel();
    expect(access.dirty).toBe(false);
    expect((await filesystem.getRootAccess()).groups).toHaveLength(1);
  });

  it('stages several issuer grants for one immutable group and removes access without deleting registration', async (): Promise<void> => {
    const { access, editor, catalogue, filesystem } = await workspace();
    editor.select('readers');
    editor.openAdd();
    editor.edit('issuer', ' second issuer ');
    editor.toggle('write', true);
    editor.apply();
    expect(editor.selected?.grants).toHaveLength(2);
    expect(access.dirty).toBe(true);
    expect((await filesystem.getRootAccess()).groups).toHaveLength(1);
    await access.save();
    expect((await filesystem.getRootAccess()).groups).toContainEqual({ issuer: ' second issuer ', group_id: 'readers', permissions: ['write'] });
    const first = editor.selected!.grants[0];
    editor.openEdit(first.id);
    editor.edit('group_id', 'different');
    editor.edit('issuer', 'revised issuer');
    editor.apply();
    expect(editor.selected?.grants[0]).toMatchObject({ group_id: 'readers', issuer: 'revised issuer' });
    for (const grant of editor.selected!.grants) access.remove(grant.id);
    expect(editor.selected?.grants).toEqual([]);
    expect(await catalogue.list()).toContainEqual({ group_id: 'readers' });
    await access.save();
    expect(access.confirmation).toBe('empty');
    await access.confirm();
    expect((await filesystem.getRootAccess()).groups).toEqual([]);
    expect(await catalogue.list()).toContainEqual({ group_id: 'readers' });
  });

  it.each(['direct', 'recursive'] as const)('rejects duplicate %s pairs but permits another issuer', async (kind): Promise<void> => {
    const catalogue: GroupCatalogue = new InMemoryGroupCatalogue([{ group_id: 'readers' }]);
    const grant = { issuer: 'issuer', group_id: 'readers', permissions: ['read' as const] };
    const filesystem: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: kind === 'direct' ? [grant] : [], unmanaged_groups: kind === 'recursive' ? [grant] : [] }));
    const access = new FilesystemAccessState(filesystem, catalogue);
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    editor.openAdd();
    editor.edit('issuer', 'issuer');
    editor.toggle('read', true);
    expect(editor.validationMessage).toBe('This issuer and group ID already have a grant.');
    editor.apply();
    expect(access.dirty).toBe(false);
    editor.edit('issuer', 'different');
    expect(editor.validationMessage).toBe('');
    editor.apply();
    expect(access.dirty).toBe(true);
  });

  it('keeps malformed legacy grants inspectable, repairable and removable', async (): Promise<void> => {
    const catalogue: GroupCatalogue = new InMemoryGroupCatalogue([{ group_id: 'registered' }]);
    const filesystem: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [
      { issuer: '', group_id: 'legacy', permissions: [] },
      { issuer: 'issuer', group_id: '', permissions: ['read'] }
    ] }));
    const access = new FilesystemAccessState(filesystem, catalogue);
    await access.load();
    const editor = new FilesystemGroupEditorState(() => access);
    expect(access.groupEntries).toHaveLength(3);
    editor.select('legacy');
    editor.openEdit(editor.selected!.grants[0].id);
    editor.edit('issuer', 'fixed');
    editor.toggle('read', true);
    editor.apply();
    expect(editor.selected?.grants[0]).toMatchObject({ issuer: 'fixed', group_id: 'legacy', permissions: ['read'] });
    editor.select('');
    editor.openEdit(editor.selected!.grants[0].id);
    expect(editor.canRepairGroupId).toBe(true);
    editor.edit('group_id', 'registered');
    editor.apply();
    expect(editor.selected?.group_id).toBe('registered');
    expect(access.canSave).toBe(true);
    await access.save();
    editor.select('legacy');
    access.remove(editor.selected!.grants[0].id);
    expect(access.groupEntries.some((group) => group.group_id === 'legacy')).toBe(false);
    expect(await catalogue.list()).toEqual([{ group_id: 'registered' }]);
  });

  it('preserves an unsaved filesystem draft when registration succeeds or is cancelled', async (): Promise<void> => {
    const { access, editor, catalogue, filesystem } = await workspace();
    access.toggle(access.rows[0].id, 'write', true);
    const draft = access.groups;
    const registration = new GroupRegistrationState(access.registerGroup, editor.select);
    registration.show();
    registration.edit('pending-group');
    registration.cancel();
    expect(access.groups).toEqual(draft);
    expect(access.dirty).toBe(true);
    expect(await catalogue.list()).not.toContainEqual({ group_id: 'pending-group' });
    registration.show();
    registration.edit('registered-group');
    await registration.submit();
    expect(access.groups).toEqual(draft);
    expect(access.dirty).toBe(true);
    expect(editor.selected?.grants).toEqual([]);
    expect((await filesystem.getRootAccess()).groups[0].permissions).toEqual(['read']);
    access.requestReload();
    await access.confirm();
    expect(access.dirty).toBe(false);
    expect(await catalogue.list()).toContainEqual({ group_id: 'registered-group' });
  });

  it('keeps registration failures separate from policy changes', async (): Promise<void> => {
    const { access } = await workspace();
    const registration = new GroupRegistrationState(async (): Promise<void> => { throw new Error('Failure'); }, (): void => {});
    registration.show();
    registration.edit(' ');
    expect(registration.valid).toBe(false);
    registration.edit('valid');
    await registration.submit();
    expect(registration.open).toBe(true);
    expect(registration.pending).toBe(false);
    expect(registration.error).toContain('could not be registered');
    expect(access.dirty).toBe(false);
  });
});
