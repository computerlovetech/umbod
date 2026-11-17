import { describe, expect, it, vi } from 'vitest';
import { InMemoryNamespaceAdministration } from '../../../../../tests/support/filesystem/in-memory-namespace-administration';
import { deferred } from '#lib/files/fixtures.test-support.js';
import type { SharedNamespace } from '#lib/admin/filesystem/domain/namespaces.js';
import { createWorkspace } from './workspace.test-support';

describe('persistent group permissions state', (): void => {
  it('loads connectors once and retains drafts across namespace tab activation', async (): Promise<void> => {
    const { state, detail, targets } = createWorkspace();
    state.activate('connectors');
    await vi.waitFor(() => expect(state.connectors?.editorStatus).toBe('ready'));
    state.connectors!.setConnectorPermission('reports', true);
    state.activate('filesystem');
    state.activate('connectors');
    expect(state.connectors?.hasUnsavedChanges).toBe(true);
    expect(detail).toHaveBeenCalledTimes(1);
    expect(targets).toHaveBeenCalledTimes(1);
    state.dispose();
  });

  it('retains group selection across namespace tab activation', async (): Promise<void> => {
    const { state } = createWorkspace();
    state.activate('filesystem');
    state.requestSelection('b');
    state.activate('connectors');
    await vi.waitFor(() => expect(state.connectors?.editorStatus).toBe('ready'));
    expect(state.connectors?.selectedGroupId).toBe('b');
    state.dispose();
  });

  it('guards group changes against hidden connector drafts and supports cancel or discard', async (): Promise<void> => {
    const { state } = createWorkspace();
    state.activate('connectors');
    await vi.waitFor(() => expect(state.connectors?.editorStatus).toBe('ready'));
    state.connectors!.setConnectorPermission('reports', true);
    state.activate('filesystem');
    state.requestSelection('b');
    expect(state.pendingSelection).toBe('b');
    expect(state.selectedGroupId).toBe('a');
    state.resolveSelection('cancel');
    expect(state.pendingSelection).toBeNull();
    expect(state.connectors?.hasUnsavedChanges).toBe(true);
    state.requestSelection('b');
    state.resolveSelection('discard');
    expect(state.selectedGroupId).toBe('b');
    expect(state.connectors?.hasUnsavedChanges).toBe(false);
    state.dispose();
  });

  it('loads namespaces lazily once and retains hidden drafts with cancel and discard protection for both domains', async (): Promise<void> => {
    const api = new InMemoryNamespaceAdministration([], ['a', 'b']);
    const entry = await api.create({ name: 'Research', groups: [] });
    const list = vi.spyOn(api, 'list');
    const { state } = createWorkspace(undefined, api);
    expect(list).not.toHaveBeenCalled();
    state.activate('filesystem');
    await state.namespaces.ensureLoaded();
    await vi.waitFor(() => expect(state.namespaces.busy).toBe(false));
    state.namespaces.stageAccess(entry.id, 'read');
    state.activate('connectors');
    await vi.waitFor(() => expect(state.connectors?.editorStatus).toBe('ready'));
    state.connectors!.setConnectorPermission('reports', true);
    state.activate('filesystem');
    expect(list).toHaveBeenCalledTimes(1);
    expect(state.namespaces.access(entry.id)).toBe('read');
    state.activate('connectors');
    state.requestSelection('b');
    expect(state.pendingSelection).toBe('b');
    state.resolveSelection('cancel');
    expect(state.selectedGroupId).toBe('a');
    expect(state.namespaces.hasUnsavedChanges).toBe(true);
    expect(state.connectors?.hasUnsavedChanges).toBe(true);
    state.requestSelection('b');
    state.resolveSelection('discard');
    expect(state.selectedGroupId).toBe('b');
    expect(state.namespaces.hasUnsavedChanges).toBe(false);
    expect(state.connectors?.hasUnsavedChanges).toBe(false);
    state.dispose();
  });

  it('blocks group switches while namespace permissions or metadata are saving and while the metadata editor is open', async (): Promise<void> => {
    const api = new InMemoryNamespaceAdministration([], ['a', 'b']);
    const entry = await api.create({ name: 'Research', groups: [] });
    const { state } = createWorkspace(undefined, api);
    await state.namespaces.ensureLoaded();
    const pending = deferred<SharedNamespace>();
    vi.spyOn(api, 'update').mockReturnValueOnce(pending.promise);
    state.namespaces.stageAccess(entry.id, 'read');
    const saving = state.namespaces.savePermissions();
    state.requestSelection('b');
    expect(state.selectedGroupId).toBe('a');
    expect(state.pendingSelection).toBeNull();
    pending.resolve({ ...entry, revision: 2, groups: [{ group_id: 'a', access: 'read' }] });
    await saving;
    state.namespaces.beginEdit(entry.id);
    state.requestSelection('b');
    expect(state.selectedGroupId).toBe('a');
    const metadata = deferred<SharedNamespace>();
    vi.spyOn(api, 'update').mockReturnValueOnce(metadata.promise);
    const writing = state.namespaces.save();
    state.requestSelection('b');
    expect(state.selectedGroupId).toBe('a');
    metadata.resolve({ ...entry, revision: 3, groups: [{ group_id: 'a', access: 'read' }] });
    await writing;
    state.requestSelection('b');
    expect(state.selectedGroupId).toBe('b');
    state.dispose();
  });

  it('observes identity before lazy namespace activation and clears drafts on replacement', async (): Promise<void> => {
    const api = new InMemoryNamespaceAdministration([], ['a', 'b']);
    const entry = await api.create({ name: 'Research', groups: [] });
    const { state } = createWorkspace(undefined, api);
    state.namespaces.observeAccountIdentity({ kind: 'hidden' });
    await state.namespaces.ensureLoaded();
    state.namespaces.stageAccess(entry.id, 'read');
    const { resolveWorkspaceAccess } = await import('#lib/workspace/admin-access.js');
    const { InMemoryWorkspaceApi } = await import('#lib/workspace/in-memory-api.test-support.js');
    const identity = await resolveWorkspaceAccess(new InMemoryWorkspaceApi({ identity_key: 'replacement', user: { id: 'replacement', name: 'Administrator', email: null, picture: null }, capabilities: { administration: true } }));
    state.namespaces.observeAccountIdentity(identity.accountIdentity);
    expect(state.namespaces.hasUnsavedChanges).toBe(false);
    await vi.waitFor(() => expect(state.namespaces.busy).toBe(false));
    expect(state.namespaces.access(entry.id)).toBe('none');
    state.dispose();
  });

  it('does not invent group registrations from legacy root grants', (): void => {
    const { state, detail } = createWorkspace();
    state.requestSelection('orphan');
    expect(state.selectedGroupId).toBe('a');
    expect(state.groupEntries.map((group) => group.group_id)).toEqual(['a', 'b']);
    expect(detail).not.toHaveBeenCalled();
    state.dispose();
  });

  it('ignores activation after disposal', (): void => {
    const { state, detail } = createWorkspace();
    state.dispose();
    state.activate('connectors');
    expect(state.connectors).toBeNull();
    expect(detail).not.toHaveBeenCalled();
  });
});
