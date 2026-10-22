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

const unavailableGrantData = (): GroupPermissionsInitialData => ({
  ...data(['a', 'b']),
  preloadedGroup: {
    groupId: 'a',
    connectorIds: ['z-unavailable', 'available', 'other-unavailable'],
    capabilities: [
      { connectorId: 'z-unavailable', kind: 'tool', key: 'removed-tool' },
      { connectorId: 'z-unavailable', kind: 'prompt', key: 'removed-prompt' },
      { connectorId: 'capability-only', kind: 'resource', key: 'removed-resource' },
      { connectorId: 'available', kind: 'tool', key: 'retained-tool' },
      { connectorId: 'other-unavailable', kind: 'prompt', key: 'retained-prompt' }
    ]
  },
  assignableTargets: targets('available')
});

describe('unavailable saved connector grants', () => {
  test('derives sorted unique IDs including capability-only grants without synthesizing permissions', () => {
    const initial = unavailableGrantData();
    const loader = new ControllableLoader();
    const state = new GroupPermissionsState(initial, null, null, loader);

    expect(state.unavailableGrantedConnectorIds).toEqual(['capability-only', 'other-unavailable', 'z-unavailable']);
    expect(state.selectedPermissionSet).toEqual(initial.preloadedGroup);
    expect(state.hasUnsavedChanges).toBe(false);
    expect(JSON.parse(state.selectedPermissionChangesJson)).toEqual({ connectors: [], capabilities: [] });
    expect(loader.groupCalls).toEqual([]);
    expect(loader.targetCalls).toBe(0);
  });

  test('stages only disabled changes for the requested connector and all its capabilities', () => {
    const initial = unavailableGrantData();
    const state = new GroupPermissionsState(initial, null, null, new ControllableLoader());
    const otherGroups = state.groups.filter((group) => group.groupId !== 'a');

    state.removeUnavailableConnectorGrants('z-unavailable');

    expect(state.unavailableGrantedConnectorIds).toEqual(['capability-only', 'other-unavailable']);
    expect(state.selectedPermissionSet).toEqual({
      ...initial.preloadedGroup,
      connectorIds: ['available', 'other-unavailable'],
      capabilities: initial.preloadedGroup?.capabilities.filter((capability) => capability.connectorId !== 'z-unavailable')
    });
    expect(state.groups.find((group) => group.groupId === 'a')).toEqual(initial.preloadedGroup);
    expect(state.groups.filter((group) => group.groupId !== 'a')).toEqual(otherGroups);
    expect(state.hasUnsavedChanges).toBe(true);
    expect(JSON.parse(state.selectedPermissionChangesJson)).toEqual({
      connectors: [{ connector_id: 'z-unavailable', permission_status: 'disabled' }],
      capabilities: [
        { connector_id: 'z-unavailable', capability_kind: 'prompt', capability_key: 'removed-prompt', permission_status: 'disabled' },
        { connector_id: 'z-unavailable', capability_kind: 'tool', capability_key: 'removed-tool', permission_status: 'disabled' }
      ]
    });
  });

  test('capability-only removal does not synthesize a connector disable or enable', () => {
    const state = new GroupPermissionsState(unavailableGrantData(), null, null, new ControllableLoader());
    state.removeUnavailableConnectorGrants('capability-only');

    expect(state.unavailableGrantedConnectorIds).toEqual(['other-unavailable', 'z-unavailable']);
    expect(JSON.parse(state.selectedPermissionChangesJson)).toEqual({
      connectors: [],
      capabilities: [{ connector_id: 'capability-only', capability_kind: 'resource', capability_key: 'removed-resource', permission_status: 'disabled' }]
    });
    const changes = state.selectedPermissionChangesJson;
    state.removeUnavailableConnectorGrants('capability-only');
    expect(state.selectedPermissionChangesJson).toBe(changes);
  });

  test.each(['available', 'unknown'])('does not remove or create grants for %s targets', (connectorId) => {
    const initial = unavailableGrantData();
    const state = new GroupPermissionsState(initial, null, null, new ControllableLoader());
    state.removeUnavailableConnectorGrants(connectorId);
    expect(state.selectedPermissionSet).toEqual(initial.preloadedGroup);
    expect(state.hasUnsavedChanges).toBe(false);
  });

  test.each(['loading', 'failed'] as const)('does not stage removal while editor is %s', async (status) => {
    const initial = unavailableGrantData();
    const loader = new ControllableLoader();
    loader.targetFailure = true;
    const state = new GroupPermissionsState(initial, null, null, loader);
    state.markGroupSaveRejected('a', 'Reload targets');
    if (status === 'failed') await vi.waitFor(() => expect(state.editorStatus).toBe('failed'));
    expect(state.editorStatus).toBe(status);
    state.removeUnavailableConnectorGrants('z-unavailable');
    expect(state.selectedPermissionSet).toEqual(initial.preloadedGroup);
    expect(state.hasUnsavedChanges).toBe(false);
  });

  test('does not stage removal without a selected group', () => {
    const state = new GroupPermissionsState(data(['a']), null, null, new ControllableLoader());
    state.removeUnavailableConnectorGrants('unknown');
    expect(state.editorStatus).toBe('unselected');
    expect(state.unavailableGrantedConnectorIds).toEqual([]);
    expect(state.selectedPermissionSet).toBeNull();
    expect(state.hasUnsavedChanges).toBe(false);
  });
});

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
