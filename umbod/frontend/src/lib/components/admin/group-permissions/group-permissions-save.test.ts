import { describe, expect, test, vi } from 'vitest';
import type { GroupPermissionSet, UpdateGroupPermissionsRequest } from '$lib/admin/group-permissions';
import type { GroupPermissionsLoader } from './group-permissions-loader';
import type { GroupPermissionsSaver } from './group-permissions-saver';
import { GroupPermissionsState, type GroupPermissionsInitialData } from './group-permissions-state.svelte';

class ControllableSaver implements GroupPermissionsSaver {
  calls: Array<{ groupId: string; changes: UpdateGroupPermissionsRequest }> = [];
  complete!: (value: GroupPermissionSet) => void;
  reject!: (reason: Error) => void;

  save(groupId: string, changes: UpdateGroupPermissionsRequest): Promise<GroupPermissionSet> {
    this.calls.push({ groupId, changes });
    return new Promise((resolve, reject) => { this.complete = resolve; this.reject = reject; });
  }
}

const initialData = (): GroupPermissionsInitialData => ({
  groups: ['a', 'b'].map((groupId) => ({ groupId, label: groupId, description: '', revision: 1 })),
  preloadedGroup: { groupId: 'a', connectorIds: [], capabilities: [] },
  assignableTargets: [{ id: 'target', displayName: 'Target', description: '', capabilities: [{ kind: 'tool', key: 'operation', label: 'Operation', description: '' }] }],
  exactMatchGuidance: '', initialTarget: null, originHref: null
});

const createLoader = (): GroupPermissionsLoader => ({
  loadGroup: vi.fn(async (groupId: string): Promise<GroupPermissionSet> => ({ groupId, connectorIds: [], capabilities: [] })),
  loadAssignableTargets: vi.fn(async () => initialData().assignableTargets)
});

const setup = (): { state: GroupPermissionsState; saver: ControllableSaver; loader: GroupPermissionsLoader } => {
  const saver = new ControllableSaver();
  const loader = createLoader();
  const state = new GroupPermissionsState(initialData(), 'Previous message', null, loader, saver);
  state.setConnectorPermission('draft', true);
  return { state, saver, loader };
};

describe('state-owned connector permission saves', () => {
  test('completes without a mounted editor and reconciles canonical permissions in place', async (): Promise<void> => {
    const { state, saver, loader } = setup();
    state.toggleConnectorExpansion('target');
    const pending = state.save();
    expect(state.saving).toBe(true);
    expect(state.canSave).toBe(false);
    expect(state.saveMessage).toBeNull();
    expect(await state.save()).toBe(false);
    state.selectGroup('b');
    state.ensureSelection('b');
    state.setConnectorPermission('late', true);
    state.setCapabilityPermission({ connectorId: 'target', kind: 'tool', key: 'operation' }, true);
    state.discardSelectedDraft();
    expect(state.selectedGroupId).toBe('a');
    expect(state.selectedPermissionSet?.connectorIds).toEqual(['draft']);
    expect(saver.calls).toEqual([{ groupId: 'a', changes: { connectors: [{ connector_id: 'draft', permission_status: 'enabled' }], capabilities: [] } }]);
    const canonical = { groupId: 'a', connectorIds: ['canonical'], capabilities: [] };
    saver.complete(canonical);
    expect(await pending).toBe(true);
    expect(state.saving).toBe(false);
    expect(state.selectedPermissionSet).toEqual(canonical);
    expect(state.groups.find((group) => group.groupId === 'a')).toEqual(canonical);
    expect(state.hasUnsavedChanges).toBe(false);
    expect(state.expandedConnectorId).toBe('target');
    expect(loader.loadGroup).not.toHaveBeenCalled();
    state.selectGroup('b');
    await vi.waitFor(() => expect(state.editorStatus).toBe('ready'));
    state.selectGroup('a');
    await vi.waitFor(() => expect(state.editorStatus).toBe('ready'));
    expect(state.selectedPermissionSet).toEqual(canonical);
    expect(loader.loadGroup).toHaveBeenCalledTimes(1);
  });

  test('rejections preserve the captured draft and permit retry', async (): Promise<void> => {
    const { state, saver } = setup();
    const draft = state.selectedPermissionSet;
    const pending = state.save();
    saver.reject(new Error('Unavailable'));
    expect(await pending).toBe(false);
    expect(state.selectedPermissionSet).toEqual(draft);
    expect(state.saveMessage).toContain('could not be saved');
    expect(state.canSave).toBe(true);
    const retry = state.save();
    expect(state.saveMessage).toBeNull();
    saver.complete({ groupId: 'a', connectorIds: ['draft'], capabilities: [] });
    expect(await retry).toBe(true);
    expect(saver.calls).toHaveLength(2);
  });

  test.each(['success', 'failure'] as const)('fences %s completion after disposal', async (outcome): Promise<void> => {
    const { state, saver } = setup();
    const pending = state.save();
    state.dispose();
    const snapshot = state.pageData;
    if (outcome === 'success') saver.complete({ groupId: 'a', connectorIds: ['obsolete'], capabilities: [] });
    else saver.reject(new Error('Obsolete'));
    expect(await pending).toBe(false);
    expect(state.pageData).toBe(snapshot);
    expect(state.saveMessage).toBeNull();
    expect(state.canSave).toBe(false);
    expect(await state.save()).toBe(false);
  });

  test('does not submit clean, unselected or loading editors', async (): Promise<void> => {
    const saver = new ControllableSaver();
    const loader = createLoader();
    const state = new GroupPermissionsState(initialData(), null, null, loader, saver);
    expect(await state.save()).toBe(false);
    const empty = { ...initialData(), preloadedGroup: null };
    const unselected = new GroupPermissionsState(empty, null, null, loader, saver);
    expect(await unselected.save()).toBe(false);
    unselected.selectGroup('a');
    expect(await unselected.save()).toBe(false);
    expect(saver.calls).toEqual([]);
  });

  test('discards the selected draft without selecting or loading the pending group', (): void => {
    const { state, loader } = setup();
    state.selectGroup('b');
    expect(state.unsavedChangesWarning).not.toBeNull();
    state.discardSelectedDraft();
    expect(state.selectedGroupId).toBe('a');
    expect(state.hasUnsavedChanges).toBe(false);
    expect(state.unsavedChangesWarning).toBeNull();
    expect(state.pageData.pendingGroupId).toBeNull();
    expect(state.editorStatus).toBe('ready');
    expect(loader.loadGroup).not.toHaveBeenCalled();
  });

  test('ensures an active selection without restarting loading or clearing expansion', async (): Promise<void> => {
    const loader = createLoader();
    const state = new GroupPermissionsState({ ...initialData(), preloadedGroup: null }, null, 'a', loader);
    state.ensureSelection('a');
    state.ensureSelection('a');
    await vi.waitFor(() => expect(state.editorStatus).toBe('ready'));
    state.toggleConnectorExpansion('target');
    state.ensureSelection('a');
    expect(state.expandedConnectorId).toBe('target');
    expect(loader.loadGroup).toHaveBeenCalledTimes(1);
    expect(loader.loadAssignableTargets).toHaveBeenCalledTimes(1);
  });

  test('refreshes changed route targets and honors explicit null without resetting ordinary tab returns', async (): Promise<void> => {
    let target: { connectorId: string; operationId: string } | null = { connectorId: 'target', operationId: 'operation' };
    const state = new GroupPermissionsState({ ...initialData(), preloadedGroup: null, initialTarget: { connectorId: 'fallback', operationId: 'fallback' } }, null, 'a', createLoader(), new ControllableSaver(), () => target);
    await vi.waitFor(() => expect(state.editorStatus).toBe('ready'));
    expect(state.expandedConnectorId).toBe('target');
    expect(state.selectedOperationId).toBe('operation');
    state.toggleConnectorExpansion('target');
    state.refreshRouteTarget();
    state.ensureSelection('a');
    expect(state.expandedConnectorId).toBeNull();
    target = null;
    state.refreshRouteTarget();
    expect(state.initialTarget).toBeNull();
    expect(state.deepLinkedTargetAvailable).toBe(true);
    target = { connectorId: 'target', operationId: 'operation' };
    state.refreshRouteTarget();
    expect(state.expandedConnectorId).toBe('target');
  });
});
