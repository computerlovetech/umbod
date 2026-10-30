import { describe, expect, it, vi } from 'vitest';
import { createWorkspace } from './workspace.test-support';

describe('persistent group permissions state', () => {
  it('loads each editor once and retains independent drafts across tab activation', async (): Promise<void> => {
    const fixture = createWorkspace();
    const { state } = fixture;
    state.activate('connectors');
    await vi.waitFor(() => expect(state.connectors?.editorStatus).toBe('ready'));
    state.connectors!.setConnectorPermission('reports', true);
    state.activate('filesystem');
    await vi.waitFor(() => expect(state.filesystem.saved).not.toBeNull());
    state.filesystemEditor.toggle('read', true);
    state.activate('connectors');
    state.activate('filesystem');
    expect(state.connectors?.hasUnsavedChanges).toBe(true);
    expect(state.filesystem.dirty).toBe(true);
    expect(state.filesystemEditor.permissions).toContain('read');
    expect(fixture.list).not.toHaveBeenCalled();
    expect(fixture.detail).toHaveBeenCalledTimes(1);
    expect(fixture.targets).toHaveBeenCalledTimes(1);
    expect(fixture.root).toHaveBeenCalledTimes(1);
    state.dispose();
  });

  it('shares group selection while retaining staged filesystem permissions', async (): Promise<void> => {
    const { state } = createWorkspace();
    state.activate('filesystem');
    await vi.waitFor(() => expect(state.filesystem.saved).not.toBeNull());
    state.filesystemEditor.toggle('read', true);
    state.requestSelection('b');
    expect(state.filesystemEditor.selected?.group_id).toBe('b');
    state.activate('connectors');
    await vi.waitFor(() => expect(state.connectors?.editorStatus).toBe('ready'));
    expect(state.connectors?.selectedGroupId).toBe('b');
    state.requestSelection('a');
    expect(state.filesystem.groups.find((group) => group.group_id === 'a')?.permissions).toContain('read');
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

  it('retains orphan IDs without inventing connector registrations', async (): Promise<void> => {
    const { state, detail } = createWorkspace();
    state.activate('filesystem');
    await vi.waitFor(() => expect(state.filesystem.saved).not.toBeNull());
    state.requestSelection('orphan');
    state.activate('connectors');
    expect(state.selectedGroup?.registered).toBe(false);
    expect(state.connectors?.selectedGroupId).toBeNull();
    expect(detail).not.toHaveBeenCalled();
    state.dispose();
  });

  it('fences late loads and future activation when the section is disposed', async (): Promise<void> => {
    const { state, filesystem, root } = createWorkspace();
    let resolve!: (policy: Awaited<ReturnType<typeof filesystem.getRootAccess>>) => void;
    root.mockImplementation(() => new Promise((complete) => { resolve = complete; }));
    state.activate('filesystem');
    state.dispose();
    resolve({ status: 'ready', revision: 'late', groups: [], blocked_group_ids: [] });
    await Promise.resolve();
    await Promise.resolve();
    expect(state.filesystem.saved).toBeNull();
    state.activate('connectors');
    expect(state.connectors).toBeNull();
  });
});
