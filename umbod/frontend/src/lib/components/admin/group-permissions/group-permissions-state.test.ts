import { describe, expect, test, vi } from 'vitest';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import type { GroupPermissionsLoader } from './group-permissions-loader';
import {
  GroupPermissionsState,
  type ConnectorPermissionTarget,
  type GroupPermissionSet,
  type GroupPermissionsInitialData
} from './group-permissions-state.svelte';

const data = (groups: string[]): GroupPermissionsInitialData => ({
  groups: groups.map((groupId) => ({ groupId })),
  preloadedGroup: null,
  assignableTargets: [],
  exactMatchGuidance: '',
  initialTarget: null,
  originHref: null
});

const detail = (groupId: string, connectorIds: string[] = []): GroupPermissionSet => ({ groupId, connectorIds, capabilities: [] });
const targets = (id: string): ConnectorPermissionTarget[] => [{ id, displayName: id, description: '', capabilities: [] }];

class ControllableLoader implements GroupPermissionsLoader {
  groups = new Map<string, GroupPermissionSet>();
  targetValue = targets('target');
  groupCalls: string[] = [];
  targetCalls = 0;
  groupFailures = new Set<string>();
  targetFailure = false;
  groupGate: ((value: GroupPermissionSet) => void) | null = null;
  targetGates: Array<(value: ConnectorPermissionTarget[]) => void> = [];

  async loadGroup(groupId: string): Promise<GroupPermissionSet> {
    this.groupCalls.push(groupId);
    if (this.groupFailures.delete(groupId)) throw new BrowserRequestError(503);
    if (this.groupGate !== null) return await new Promise((resolve) => { this.groupGate = resolve; });
    const value = this.groups.get(groupId);
    if (value === undefined) throw new Error(`missing ${groupId}`);
    return structuredClone(value);
  }

  async loadAssignableTargets(): Promise<ConnectorPermissionTarget[]> {
    this.targetCalls += 1;
    if (this.targetFailure) {
      this.targetFailure = false;
      throw new BrowserRequestError(503);
    }
    if (this.targetGates.length > 0) return await new Promise((resolve) => this.targetGates.push(resolve));
    return structuredClone(this.targetValue);
  }
}

const ready = async (state: GroupPermissionsState): Promise<void> => {
  await vi.waitFor(() => expect(state.editorStatus).toBe('ready'));
};

describe('GroupPermissionsState public behavior', () => {
  test('uses server-preloaded selection without hydration requests', () => {
    const loader = new ControllableLoader();
    const initialData = data(['a']);
    initialData.preloadedGroup = detail('a', ['preloaded']);
    initialData.assignableTargets = targets('preloaded');
    const state = new GroupPermissionsState(initialData, null, null, loader);

    expect(state.selectedGroupId).toBe('a');
    expect(state.editorStatus).toBe('ready');
    expect(state.selectedPermissionSet?.connectorIds).toEqual(['preloaded']);
    expect(state.connectors).toEqual(targets('preloaded'));
    expect(loader.groupCalls).toEqual([]);
    expect(loader.targetCalls).toBe(0);
  });

  test('a late selection response cannot overwrite active targets', async () => {
    const loader = new ControllableLoader();
    loader.groups.set('a', detail('a'));
    loader.groups.set('b', detail('b'));
    loader.targetGates.push(() => undefined);
    const state = new GroupPermissionsState(data(['a', 'b']), null, null, loader);
    state.selectGroup('a');
    await vi.waitFor(() => expect(loader.targetCalls).toBe(1));
    state.selectGroup('b');
    await vi.waitFor(() => expect(loader.targetCalls).toBe(2));
    loader.targetGates[2]?.(targets('current'));
    await ready(state);
    loader.targetGates[1]?.(targets('stale'));
    await Promise.resolve();
    expect(state.connectors.map((target) => target.id)).toEqual(['current']);
  });

  test('partial success is cached independently while the failed resource retries', async () => {
    const loader = new ControllableLoader();
    loader.groups.set('a', detail('a'));
    loader.targetFailure = true;
    const state = new GroupPermissionsState(data(['a']), null, null, loader);
    state.selectGroup('a');
    await vi.waitFor(() => expect(state.editorStatus).toBe('failed'));
    state.retrySelection();
    await ready(state);
    expect(loader.groupCalls).toEqual(['a']);
    expect(loader.targetCalls).toBe(2);
  });

  test('successful targets remain cached when group detail fails', async () => {
    const loader = new ControllableLoader();
    loader.groups.set('a', detail('a'));
    loader.groupFailures.add('a');
    const state = new GroupPermissionsState(data(['a']), null, null, loader);
    state.selectGroup('a');
    await vi.waitFor(() => expect(state.editorStatus).toBe('failed'));
    state.retrySelection();
    await ready(state);
    expect(loader.groupCalls).toEqual(['a', 'a']);
    expect(loader.targetCalls).toBe(1);
  });

  test('discard removes the previous selected group draft', async () => {
    const loader = new ControllableLoader();
    loader.groups.set('a', detail('a'));
    loader.groups.set('b', detail('b'));
    const state = new GroupPermissionsState(data(['a', 'b']), null, null, loader);
    state.selectGroup('a');
    await ready(state);
    state.setConnectorPermission('changed', true);
    state.selectGroup('b');
    state.resolveUnsavedChanges('discard');
    await ready(state);
    state.selectGroup('a');
    await ready(state);
    expect(state.hasUnsavedChanges).toBe(false);
  });

  test('rejected save preserves draft and invalidates assignable targets', async () => {
    const loader = new ControllableLoader();
    loader.groups.set('a', detail('a'));
    const state = new GroupPermissionsState(data(['a']), null, null, loader);
    state.selectGroup('a');
    await ready(state);
    state.setConnectorPermission('changed', true);
    state.markGroupSaveRejected('a', 'Could not save permissions');
    await ready(state);
    expect(state.hasUnsavedChanges).toBe(true);
    expect(loader.targetCalls).toBe(2);
  });

  test('successful save always reloads canonical group detail', async () => {
    const loader = new ControllableLoader();
    loader.groups.set('a', detail('a'));
    const state = new GroupPermissionsState(data(['a']), null, null, loader);
    state.selectGroup('a');
    await ready(state);
    state.setConnectorPermission('draft', true);
    loader.groups.set('a', detail('a', ['canonical']));
    state.markGroupSaved('a');
    await ready(state);
    expect(state.selectedPermissionSet?.connectorIds).toEqual(['canonical']);
    expect(loader.groupCalls).toEqual(['a', 'a']);
  });

  test('deletion synchronization prunes cached detail before re-registration', async () => {
    const loader = new ControllableLoader();
    loader.groups.set('a', detail('a', ['old']));
    const state = new GroupPermissionsState(data(['a']), null, null, loader);
    state.selectGroup('a');
    await ready(state);
    state.synchronizeServerData(data([]), null, null);
    loader.groups.set('a', detail('a', ['new']));
    state.synchronizeServerData(data(['a']), null, 'a');
    await ready(state);
    expect(state.selectedPermissionSet?.connectorIds).toEqual(['new']);
    expect(loader.groupCalls).toEqual(['a', 'a']);
  });
});
