import { capabilityKindSections, capabilityPermissionId, permissionSetDifference, type CapabilityKind } from '$lib/admin/group-permissions';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import { BrowserGroupPermissionsLoader, type GroupPermissionsLoader } from './group-permissions-loader';

export type GroupPermissionCapabilityRef = {
  connectorId: string;
  kind: CapabilityKind;
  key: string;
};

export type GroupPermissionToolRef = {
  connectorId: string;
  operationName: string;
};

export type GroupPermissionSet = {
  groupId: string;
  connectorIds: string[];
  capabilities: GroupPermissionCapabilityRef[];
};

export type ConnectorCapability = {
  kind: CapabilityKind;
  key: string;
  label: string;
  description: string;
};

export type ConnectorTool = {
  operationName: string;
  label: string;
  description: string;
};

export type ConnectorPermissionTarget = {
  id: string;
  displayName: string;
  description: string;
  capabilities: ConnectorCapability[];
};

export type GroupPermissionsInitialData = {
  groups: Array<{ groupId: string }>;
  preloadedGroup: GroupPermissionSet | null;
  assignableTargets: ConnectorPermissionTarget[];
  exactMatchGuidance: string;
  initialTarget: { connectorId: string; operationId: string } | null;
  originHref: string | null;
};

type UnsavedChangesDecision = 'cancel' | 'discard';

type ResolveUnsavedChangesResult = {
  pageData: Record<string, unknown>;
  selectedGroupId: string | null;
};

const groupsFromState = (pageData: Record<string, unknown>): GroupPermissionSet[] => {
  return Array.isArray(pageData.groups) ? (pageData.groups as GroupPermissionSet[]) : [];
};

const stagedFromState = (pageData: Record<string, unknown>): Record<string, GroupPermissionSet> => {
  return isRecord(pageData.stagedPermissions) ? (pageData.stagedPermissions as Record<string, GroupPermissionSet>) : {};
};

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
};

const clonePermissionSet = (permissionSet: GroupPermissionSet): GroupPermissionSet => {
  return {
    groupId: permissionSet.groupId,
    connectorIds: [...permissionSet.connectorIds],
    capabilities: permissionSet.capabilities.map((capability) => ({ ...capability }))
  };
};

const emptyPermissionSet = (groupId: string): GroupPermissionSet => {
  return { groupId, connectorIds: [], capabilities: [] };
};

const permissionSetForStaging = (pageData: Record<string, unknown>, groupId: string): GroupPermissionSet => {
  return clonePermissionSet(
    stagedPermissionSetFromState(pageData, groupId) ?? persistedPermissionSetFromState(pageData, groupId) ?? emptyPermissionSet(groupId)
  );
};

const withStagedPermissionSet = (pageData: Record<string, unknown>, permissionSet: GroupPermissionSet): Record<string, unknown> => {
  return {
    ...pageData,
    currentGroupId: permissionSet.groupId,
    stagedPermissions: {
      ...stagedFromState(pageData),
      [permissionSet.groupId]: clonePermissionSet(permissionSet)
    }
  };
};

const permissionSetsAreEqual = (first: GroupPermissionSet | null, second: GroupPermissionSet | null): boolean => {
  if (first === null || second === null) {
    return first === second;
  }

  return JSON.stringify(normalizePermissionSet(first)) === JSON.stringify(normalizePermissionSet(second));
};

const normalizePermissionSet = (permissionSet: GroupPermissionSet): GroupPermissionSet => {
  return {
    groupId: permissionSet.groupId,
    connectorIds: [...permissionSet.connectorIds].sort(),
    capabilities: [...permissionSet.capabilities].sort((first, second) => {
      return capabilityPermissionId(first).localeCompare(capabilityPermissionId(second));
    })
  };
};

export const addGroupToState = (pageData: Record<string, unknown>, groupId: string): Record<string, unknown> => {
  if (groupId.trim() === '') {
    return { ...pageData, validationMessage: 'Group value is required' };
  }

  const groups = groupsFromState(pageData);
  const existingGroup = groups.find((group) => group.groupId === groupId);
  const nextGroups = existingGroup === undefined ? [...groups, emptyPermissionSet(groupId)] : groups;
  const stagedNewGroupIds = Array.isArray(pageData.stagedNewGroupIds) ? (pageData.stagedNewGroupIds as string[]) : [];

  return withStagedPermissionSet(
    {
      ...pageData,
      groups: nextGroups,
      stagedNewGroupIds: existingGroup === undefined && !stagedNewGroupIds.includes(groupId) ? [...stagedNewGroupIds, groupId] : stagedNewGroupIds,
      validationMessage: null
    },
    existingGroup ?? emptyPermissionSet(groupId)
  );
};

export const grantPermissionInState = (
  pageData: Record<string, unknown>,
  groupId: string,
  capability: { connectorId: string; kind?: CapabilityKind; key?: string }
): Record<string, unknown> => {
  const permissionSet = permissionSetForStaging(pageData, groupId);

  if (!permissionSet.connectorIds.includes(capability.connectorId)) {
    permissionSet.connectorIds = [...permissionSet.connectorIds, capability.connectorId];
  }

  if (
    capability.kind !== undefined &&
    capability.key !== undefined &&
    !permissionSet.capabilities.some(
      (existing) =>
        existing.connectorId === capability.connectorId &&
        existing.kind === capability.kind &&
        existing.key === capability.key
    )
  ) {
    permissionSet.capabilities = [
      ...permissionSet.capabilities,
      { connectorId: capability.connectorId, kind: capability.kind, key: capability.key }
    ];
  }

  return withStagedPermissionSet(pageData, permissionSet);
};

export const revokeConnectorFromState = (pageData: Record<string, unknown>, groupId: string, connectorId: string): Record<string, unknown> => {
  const permissionSet = permissionSetForStaging(pageData, groupId);
  permissionSet.connectorIds = permissionSet.connectorIds.filter((existing) => existing !== connectorId);
  permissionSet.capabilities = permissionSet.capabilities.filter((capability) => capability.connectorId !== connectorId);
  return withStagedPermissionSet(pageData, permissionSet);
};

export const revokeCapabilityFromState = (
  pageData: Record<string, unknown>,
  groupId: string,
  capability: GroupPermissionCapabilityRef
): Record<string, unknown> => {
  const permissionSet = permissionSetForStaging(pageData, groupId);
  permissionSet.capabilities = permissionSet.capabilities.filter(
    (existing) =>
      existing.connectorId !== capability.connectorId ||
      existing.kind !== capability.kind ||
      existing.key !== capability.key
  );
  if (!permissionSet.capabilities.some((existing) => existing.connectorId === capability.connectorId)) {
    permissionSet.connectorIds = permissionSet.connectorIds.filter((connectorId) => connectorId !== capability.connectorId);
  }
  return withStagedPermissionSet(pageData, permissionSet);
};

export const revokeToolFromState = (
  pageData: Record<string, unknown>,
  groupId: string,
  tool: GroupPermissionToolRef
): Record<string, unknown> => {
  return revokeCapabilityFromState(pageData, groupId, {
    connectorId: tool.connectorId,
    kind: 'tool',
    key: tool.operationName
  });
};

export const stagedPermissionSetFromState = (pageData: Record<string, unknown>, groupId: string): GroupPermissionSet | null => {
  const permissionSet = stagedFromState(pageData)[groupId];
  return permissionSet === undefined ? null : clonePermissionSet(permissionSet);
};

export const persistedPermissionSetFromState = (pageData: Record<string, unknown>, groupId: string): GroupPermissionSet | null => {
  const stagedNewGroupIds = Array.isArray(pageData.stagedNewGroupIds) ? (pageData.stagedNewGroupIds as string[]) : [];

  if (stagedNewGroupIds.includes(groupId)) {
    return null;
  }

  const permissionSet = groupsFromState(pageData).find((group) => group.groupId === groupId);
  if (permissionSet === undefined || !Array.isArray(permissionSet.connectorIds) || !Array.isArray(permissionSet.capabilities)) {
    return null;
  }
  return clonePermissionSet(permissionSet);
};

export const hasUnsavedChangesInState = (pageData: Record<string, unknown>, groupId: string): boolean => {
  const stagedPermissionSet = stagedPermissionSetFromState(pageData, groupId);
  if (stagedPermissionSet === null) {
    return false;
  }

  return !permissionSetsAreEqual(stagedPermissionSet, persistedPermissionSetFromState(pageData, groupId));
};

export const stageGroupSelectionWithUnsavedChanges = (pageData: Record<string, unknown>, groupId: string): Record<string, unknown> => {
  return {
    ...pageData,
    pendingGroupId: groupId,
    unsavedChangesWarning: 'You have unsaved changes. Discard them or cancel before switching groups.'
  };
};

export const resolveUnsavedChangesInState = (pageData: Record<string, unknown>, decision: UnsavedChangesDecision): ResolveUnsavedChangesResult => {
  if (decision === 'cancel') {
    return {
      pageData: {
        ...pageData,
        pendingGroupId: null,
        unsavedChangesWarning: null
      },
      selectedGroupId: typeof pageData.currentGroupId === 'string' ? pageData.currentGroupId : null
    };
  }

  const pendingGroupId = typeof pageData.pendingGroupId === 'string' ? pageData.pendingGroupId : null;
  const currentGroupId = typeof pageData.currentGroupId === 'string' ? pageData.currentGroupId : null;
  const stagedPermissions = { ...stagedFromState(pageData) };
  if (currentGroupId !== null) delete stagedPermissions[currentGroupId];

  return {
    pageData: {
      ...pageData,
      stagedPermissions,
      pendingGroupId: null,
      unsavedChangesWarning: null
    },
    selectedGroupId: pendingGroupId
  };
};

export class GroupPermissionsState {
  pageData = $state.raw<Record<string, unknown>>({});
  groupInput = $state('');
  saveMessage = $state<string | null>(null);
  expandedConnectorId = $state<string | null>(null);
  selectedOperationId = $state<string | null>(null);
  openGroupMenuId = $state<string | null>(null);
  connectors = $state.raw<ConnectorPermissionTarget[]>([]);
  editorStatus = $state<'unselected' | 'loading' | 'ready' | 'failed'>('unselected');
  editorError = $state<string | null>(null);
  readonly exactMatchGuidance: string;
  readonly initialTarget: { connectorId: string; operationId: string } | null;
  readonly originHref: string | null;
  deepLinkedTargetAvailable = $state(true);
  private serverData: GroupPermissionsInitialData;
  private readonly loader: GroupPermissionsLoader;
  private readonly groupCache = new Map<string, GroupPermissionSet>();
  private targetsCache: ConnectorPermissionTarget[] | null = null;
  private requestGeneration = 0;
  private abortController: AbortController | null = null;

  constructor(data: GroupPermissionsInitialData, saveMessage: string | null, selectedGroupId: string | null, loader: GroupPermissionsLoader = new BrowserGroupPermissionsLoader()) {
    const requestedGroup = data.groups.some((group) => group.groupId === selectedGroupId) ? selectedGroupId : null;
    const selectedGroup = requestedGroup ?? data.preloadedGroup?.groupId ?? null;
    if (data.preloadedGroup !== null) this.groupCache.set(data.preloadedGroup.groupId, clonePermissionSet(data.preloadedGroup));
    if (data.preloadedGroup !== null) this.targetsCache = data.assignableTargets;
    this.pageData = {
      ...data,
      groups: data.groups.map((group) => this.groupCache.get(group.groupId) ?? emptyPermissionSet(group.groupId)),
      currentGroupId: selectedGroup,
      stagedPermissions: {},
      stagedNewGroupIds: []
    };
    this.serverData = data;
    this.loader = loader;
    this.connectors = data.preloadedGroup === null ? [] : data.assignableTargets;
    this.exactMatchGuidance = data.exactMatchGuidance;
    this.initialTarget = data.initialTarget;
    this.originHref = data.originHref;
    this.applyInitialTarget(this.connectors);
    this.editorStatus = selectedGroup === null ? 'unselected' : selectedGroup === data.preloadedGroup?.groupId ? 'ready' : 'loading';
    this.saveMessage = saveMessage;
    if (selectedGroup !== null && selectedGroup !== data.preloadedGroup?.groupId) void this.loadSelection(selectedGroup);
  }

  selectedGroupId = $derived(typeof this.pageData.currentGroupId === 'string' ? this.pageData.currentGroupId : null);
  groups = $derived(groupsFromState(this.pageData));
  validationMessage = $derived(typeof this.pageData.validationMessage === 'string' ? this.pageData.validationMessage : null);
  unsavedChangesWarning = $derived(typeof this.pageData.unsavedChangesWarning === 'string' ? this.pageData.unsavedChangesWarning : null);
  selectedPermissionSet = $derived.by(() => {
    if (this.selectedGroupId === null) {
      return null;
    }

    return stagedPermissionSetFromState(this.pageData, this.selectedGroupId) ?? persistedPermissionSetFromState(this.pageData, this.selectedGroupId) ?? emptyPermissionSet(this.selectedGroupId);
  });
  selectedPermissionSetJson = $derived(JSON.stringify(this.selectedPermissionSet ?? { groupId: '', connectorIds: [], capabilities: [] }));
  selectedPermissionChangesJson = $derived.by(() => {
    if (this.selectedGroupId === null || this.selectedPermissionSet === null) {
      return JSON.stringify({ connectors: [], capabilities: [] });
    }
    const persisted = persistedPermissionSetFromState(this.pageData, this.selectedGroupId) ?? emptyPermissionSet(this.selectedGroupId);
    return JSON.stringify(permissionSetDifference(persisted, this.selectedPermissionSet));
  });
  hasUnsavedChanges = $derived(this.selectedGroupId === null ? false : hasUnsavedChangesInState(this.pageData, this.selectedGroupId));
  selectedConnectorIds = $derived(new Set(this.selectedPermissionSet?.connectorIds ?? []));
  selectedCapabilityIds = $derived(new Set((this.selectedPermissionSet?.capabilities ?? []).map(capabilityPermissionId)));
  grantedCapabilityCounts = $derived.by(() => {
    const counts = new Map<string, number>();

    for (const capability of this.selectedPermissionSet?.capabilities ?? []) {
      counts.set(capability.connectorId, (counts.get(capability.connectorId) ?? 0) + 1);
    }

    return counts;
  });

  synchronizeServerData = (data: GroupPermissionsInitialData, saveMessage: string | null, selectedGroupId: string | null): void => {
    const currentGroupIds = new Set(data.groups.map((group) => group.groupId));
    for (const cachedGroupId of this.groupCache.keys()) {
      if (!currentGroupIds.has(cachedGroupId)) this.groupCache.delete(cachedGroupId);
    }

    if (data === this.serverData) {
      if (selectedGroupId !== null && data.groups.some((group) => group.groupId === selectedGroupId)) {
        this.pageData = { ...this.pageData, currentGroupId: selectedGroupId };
        void this.loadSelection(selectedGroupId);
      }
      this.saveMessage = saveMessage;
      return;
    }

    const selectedGroup = data.groups.some((group) => group.groupId === selectedGroupId)
      ? selectedGroupId
      : data.groups.some((group) => group.groupId === this.selectedGroupId)
        ? this.selectedGroupId
        : data.preloadedGroup?.groupId ?? null;

    if (data.preloadedGroup !== null) {
      this.groupCache.set(data.preloadedGroup.groupId, clonePermissionSet(data.preloadedGroup));
      this.targetsCache = data.assignableTargets;
      this.connectors = data.assignableTargets;
    }
    this.serverData = data;
    this.pageData = {
      ...data,
      groups: data.groups.map((group) => this.groupCache.get(group.groupId) ?? emptyPermissionSet(group.groupId)),
      currentGroupId: selectedGroup,
      stagedPermissions: {},
      stagedNewGroupIds: []
    };
    this.groupInput = '';
    this.saveMessage = saveMessage;
    if (selectedGroup !== null) void this.loadSelection(selectedGroup);
  };

  updateGroupInput = (value: string): void => {
    this.groupInput = value;
  };

  addGroup = (): void => {
    this.pageData = addGroupToState(this.pageData, this.groupInput);
    if (this.validationMessage === null) {
      this.groupInput = '';
    }
  };

  selectGroup = (groupId: string): void => {
    if (this.selectedGroupId !== null && this.selectedGroupId !== groupId && this.hasUnsavedChanges) {
      this.pageData = stageGroupSelectionWithUnsavedChanges(this.pageData, groupId);
      return;
    }

    this.expandedConnectorId = null;
    this.selectedOperationId = null;
    this.openGroupMenuId = null;
    this.pageData = { ...this.pageData, currentGroupId: groupId };
    void this.loadSelection(groupId);
  };

  retrySelection = (): void => {
    if (this.selectedGroupId !== null) void this.loadSelection(this.selectedGroupId);
  };

  private loadSelection = async (groupId: string): Promise<void> => {
    const generation = ++this.requestGeneration;
    this.abortController?.abort();
    this.abortController = new AbortController();
    this.editorStatus = 'loading';
    this.editorError = null;

    try {
      const detailPromise = this.groupCache.has(groupId)
        ? Promise.resolve(this.groupCache.get(groupId) as GroupPermissionSet)
        : this.loader.loadGroup(groupId, this.abortController.signal).then((detail) => {
            this.groupCache.set(groupId, detail);
            return detail;
          });
      const targetsPromise = this.targetsCache !== null
        ? Promise.resolve(this.targetsCache)
        : this.loader.loadAssignableTargets(this.abortController.signal).then((targets) => {
            if (generation === this.requestGeneration && this.selectedGroupId === groupId) {
              this.targetsCache = targets;
            }
            return targets;
          });
      const [detail, targets] = await Promise.all([detailPromise, targetsPromise]);
      if (generation !== this.requestGeneration || this.selectedGroupId !== groupId) return;
      this.connectors = targets;
      const groups = groupsFromState(this.pageData);
      this.pageData = {
        ...this.pageData,
        groups: groups.map((group) => group.groupId === groupId ? clonePermissionSet(detail) : group)
      };
      this.editorStatus = 'ready';
      this.applyInitialTarget(targets);
    } catch (error) {
      if (generation !== this.requestGeneration || this.selectedGroupId !== groupId) return;
      if (error instanceof DOMException && error.name === 'AbortError') return;
      if (!(error instanceof BrowserRequestError)) throw error;
      this.editorStatus = 'failed';
      this.editorError = 'Permission data could not be loaded. Try again.';
    }
  };

  private applyInitialTarget = (targets: ConnectorPermissionTarget[]): void => {
    if (this.initialTarget === null) {
      this.deepLinkedTargetAvailable = true;
      this.expandedConnectorId = null;
      this.selectedOperationId = null;
      return;
    }
    const available = targets.some(
      (connector) =>
        connector.id === this.initialTarget?.connectorId &&
        connector.capabilities.some(
          (capability) => capability.kind === 'tool' && capability.key === this.initialTarget?.operationId
        )
    );
    this.deepLinkedTargetAvailable = available;
    this.expandedConnectorId = available ? this.initialTarget.connectorId : null;
    this.selectedOperationId = available ? this.initialTarget.operationId : null;
  };

  setGroupMenuOpen = (groupId: string, open: boolean): void => {
    this.openGroupMenuId = open ? groupId : null;
  };

  closeGroupMenu = (): void => {
    this.openGroupMenuId = null;
  };

  resolveUnsavedChanges = (decision: UnsavedChangesDecision): void => {
    const result = resolveUnsavedChangesInState(this.pageData, decision);
    this.pageData = { ...result.pageData, currentGroupId: result.selectedGroupId };
    if (decision === 'discard' && result.selectedGroupId !== null) void this.loadSelection(result.selectedGroupId);
  };

  markGroupSaved = (groupId: string): void => {
    const stagedPermissions = { ...stagedFromState(this.pageData) };
    const stagedNewGroupIds = Array.isArray(this.pageData.stagedNewGroupIds) ? (this.pageData.stagedNewGroupIds as string[]) : [];
    delete stagedPermissions[groupId];
    this.pageData = {
      ...this.pageData,
      currentGroupId: groupId,
      stagedPermissions,
      stagedNewGroupIds: stagedNewGroupIds.filter((stagedGroupId) => stagedGroupId !== groupId)
    };
    this.groupCache.delete(groupId);
    void this.loadSelection(groupId);
  };

  markGroupSaveRejected = (groupId: string, message: string): void => {
    this.saveMessage = message;
    this.targetsCache = null;
    if (this.selectedGroupId === groupId) void this.loadSelection(groupId);
  };

  setConnectorPermission = (connectorId: string, checked: boolean): void => {
    if (this.selectedGroupId === null) {
      return;
    }

    if (!checked && this.expandedConnectorId === connectorId) {
      this.expandedConnectorId = null;
    }

    this.pageData = checked
      ? grantPermissionInState(this.pageData, this.selectedGroupId, { connectorId })
      : revokeConnectorFromState(this.pageData, this.selectedGroupId, connectorId);
  };

  toggleConnectorExpansion = (connectorId: string): void => {
    this.expandedConnectorId = this.expandedConnectorId === connectorId ? null : connectorId;
    this.selectedOperationId = null;
  };

  grantedCapabilityCount = (connectorId: string): number => {
    return this.grantedCapabilityCounts.get(connectorId) ?? 0;
  };

  grantedToolCount = (connectorId: string): number => {
    return this.grantedCapabilityCount(connectorId);
  };

  connectorInitials = (displayName: string): string => {
    return displayName
      .split(/\s+/)
      .filter((part) => part.length > 0)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? '')
      .join('');
  };

  setCapabilityPermission = (capability: GroupPermissionCapabilityRef, checked: boolean): void => {
    if (this.selectedGroupId === null) {
      return;
    }

    this.pageData = checked
      ? grantPermissionInState(this.pageData, this.selectedGroupId, capability)
      : revokeCapabilityFromState(this.pageData, this.selectedGroupId, capability);
  };

  setToolPermission = (tool: GroupPermissionToolRef, checked: boolean): void => {
    this.setCapabilityPermission({ connectorId: tool.connectorId, kind: 'tool', key: tool.operationName }, checked);
  };

  connectorIsGranted = (connectorId: string): boolean => {
    return this.selectedConnectorIds.has(connectorId);
  };

  capabilityIsGranted = (capability: GroupPermissionCapabilityRef): boolean => {
    return this.selectedCapabilityIds.has(capabilityPermissionId(capability));
  };

  toolIsGranted = (tool: GroupPermissionToolRef): boolean => {
    return this.capabilityIsGranted({ connectorId: tool.connectorId, kind: 'tool', key: tool.operationName });
  };

  capabilitiesBySection = (connector: ConnectorPermissionTarget): Array<{ kind: CapabilityKind; label: string; capabilities: ConnectorCapability[] }> => {
    return capabilityKindSections
      .map((section) => ({
        kind: section.kind,
        label: section.label,
        capabilities: connector.capabilities.filter((capability) => capability.kind === section.kind)
      }))
      .filter((section) => section.capabilities.length > 0);
  };
}
