import { describe, expect, test, vi } from 'vitest';

type GroupPermissionToolRef = {
  connectorId: string;
  operationName: string;
};

type GroupPermissionCapabilityRef = {
  connectorId: string;
  kind: 'tool' | 'prompt' | 'resource' | 'resource_template';
  key: string;
};

type GroupPermissionSet = {
  groupId: string;
  connectorIds: string[];
  capabilities: GroupPermissionCapabilityRef[];
};

type SaveGroupPermissionsResult =
  | { status: 'saved'; groupId: string }
  | { status: 'registered'; groupId: string }
  | { status: 'rejected'; groupId: string; message: string }
  | { status: 'failed'; groupId: string; message: string };

type UnsavedChangesDecision = 'cancel' | 'discard';

type GroupPermissionsPageLoad = (event: { fetch: typeof fetch; url: URL }) => Promise<unknown>;

type GroupPermissionsPageActions = {
  registerPermissionGroup: (event: { fetch: typeof fetch; request: Request }) => Promise<unknown>;
  saveGroupPermissions: (event: { fetch: typeof fetch; request: Request }) => Promise<unknown>;
};

interface GroupPermissionsNavigationUi {
  openGroupPermissionsTab(): Promise<void>;
  reloadGroupPermissionsTab(): Promise<void>;
  visibleNavigationLabels(): Promise<string[]>;
}

interface GroupPermissionsGroupListUi {
  visibleGroupIds(): Promise<string[]>;
}

interface GroupPermissionsGroupSelectionUi {
  selectedGroupId(): Promise<string | null>;
  selectGroup(groupId: string): Promise<void>;
}

interface GroupPermissionsGroupAdditionUi {
  addGroup(groupId: string): Promise<void>;
}

interface GroupPermissionsGroupValidationUi {
  visibleValidationMessage(): Promise<string | null>;
}

interface GroupPermissionsListUi
  extends GroupPermissionsGroupListUi,
    GroupPermissionsGroupSelectionUi,
    GroupPermissionsGroupAdditionUi,
    GroupPermissionsGroupValidationUi {}

interface GroupPermissionsGuidanceUi {
  visibleExactMatchGuidance(): Promise<string>;
}

interface GroupPermissionsAssignableTargetsUi {
  visibleAssignableConnectorIds(): Promise<string[]>;
  visibleAssignableTools(): Promise<GroupPermissionToolRef[]>;
}

interface GroupPermissionsEditorUi {
  grantConnector(connectorId: string): Promise<void>;
  revokeConnector(connectorId: string): Promise<void>;
  grantTool(tool: GroupPermissionToolRef): Promise<void>;
  revokeTool(tool: GroupPermissionToolRef): Promise<void>;
  stagedPermissionSet(): Promise<GroupPermissionSet | null>;
  persistedPermissionSet(groupId: string): Promise<GroupPermissionSet | null>;
  hasUnsavedChanges(): Promise<boolean>;
}

interface GroupPermissionsSaveUi {
  saveSelectedGroupPermissions(): Promise<SaveGroupPermissionsResult>;
  visibleSaveMessage(): Promise<string | null>;
}

interface GroupPermissionsUnsavedChangesUi {
  attemptSelectGroupWithUnsavedChanges(groupId: string): Promise<void>;
  visibleUnsavedChangesWarning(): Promise<string | null>;
  resolveUnsavedChangesWarning(decision: UnsavedChangesDecision): Promise<void>;
}

interface AdminGroupPermissionsUi
  extends GroupPermissionsNavigationUi,
    GroupPermissionsListUi,
    GroupPermissionsGuidanceUi,
    GroupPermissionsAssignableTargetsUi,
    GroupPermissionsEditorUi,
    GroupPermissionsSaveUi,
    GroupPermissionsUnsavedChangesUi {}

interface GroupPermissionRuntimeProbe {
  visibleToolNamesForJwtGroups(jwtGroups: string[]): Promise<string[]>;
}

interface GroupPermissionAuthorization {
  canOpenGroupPermissionsAdmin(): Promise<boolean>;
}

type GroupPermissionsStateModule = {
  addGroupToState: (pageData: Record<string, unknown>, groupId: string) => Record<string, unknown>;
  grantPermissionInState: (
    pageData: Record<string, unknown>,
    groupId: string,
    capability: { connectorId: string; kind?: 'tool' | 'prompt' | 'resource' | 'resource_template'; key?: string }
  ) => Record<string, unknown>;
  revokeConnectorFromState: (pageData: Record<string, unknown>, groupId: string, connectorId: string) => Record<string, unknown>;
  revokeToolFromState: (pageData: Record<string, unknown>, groupId: string, tool: GroupPermissionToolRef) => Record<string, unknown>;
  stagedPermissionSetFromState: (pageData: Record<string, unknown>, groupId: string) => GroupPermissionSet | null;
  persistedPermissionSetFromState: (pageData: Record<string, unknown>, groupId: string) => GroupPermissionSet | null;
  hasUnsavedChangesInState: (pageData: Record<string, unknown>, groupId: string) => boolean;
  stageGroupSelectionWithUnsavedChanges: (pageData: Record<string, unknown>, groupId: string) => Record<string, unknown>;
  resolveUnsavedChangesInState: (
    pageData: Record<string, unknown>,
    decision: UnsavedChangesDecision
  ) => { pageData: Record<string, unknown>; selectedGroupId: string | null };
};

class AdminGroupPermissionsDsl {
  readonly navigation: AdminGroupPermissionsNavigationDsl;
  readonly list: AdminGroupPermissionsListDsl;
  readonly guidance: AdminGroupPermissionsGuidanceDsl;
  readonly targets: AdminGroupPermissionsAssignableTargetsDsl;
  readonly editor: AdminGroupPermissionsEditorDsl;
  readonly save: AdminGroupPermissionsSaveDsl;
  readonly unsaved: AdminGroupPermissionsUnsavedDsl;
  readonly runtime: AdminGroupPermissionsRuntimeDsl;
  readonly auth: AdminGroupPermissionsAuthorizationDsl;

  constructor(ui: AdminGroupPermissionsUi, runtime: GroupPermissionRuntimeProbe, authorization: GroupPermissionAuthorization) {
    this.navigation = new AdminGroupPermissionsNavigationDsl(ui);
    this.list = new AdminGroupPermissionsListDsl(ui);
    this.guidance = new AdminGroupPermissionsGuidanceDsl(ui);
    this.targets = new AdminGroupPermissionsAssignableTargetsDsl(ui);
    this.editor = new AdminGroupPermissionsEditorDsl(ui);
    this.save = new AdminGroupPermissionsSaveDsl(ui);
    this.unsaved = new AdminGroupPermissionsUnsavedDsl(ui);
    this.runtime = new AdminGroupPermissionsRuntimeDsl(runtime);
    this.auth = new AdminGroupPermissionsAuthorizationDsl(authorization);
  }
}

class AdminGroupPermissionsNavigationDsl {
  constructor(private readonly ui: GroupPermissionsNavigationUi) {}

  async openGroupPermissions(): Promise<void> {
    await this.ui.openGroupPermissionsTab();
  }

  async reloadGroupPermissions(): Promise<void> {
    await this.ui.reloadGroupPermissionsTab();
  }

  async expectGroupPermissionsNavigation(): Promise<void> {
    expect(await this.ui.visibleNavigationLabels()).toContain('Group permissions');
  }
}

class AdminGroupPermissionsListDsl {
  constructor(
    private readonly ui: GroupPermissionsGroupListUi &
      GroupPermissionsGroupAdditionUi &
      GroupPermissionsGroupSelectionUi &
      GroupPermissionsGroupValidationUi &
      GroupPermissionsEditorUi
  ) {}

  async expectExistingGroups(groupIds: string[]): Promise<void> {
    expect(await this.ui.visibleGroupIds()).toEqual(expect.arrayContaining(groupIds));
  }

  async addGroup(groupId: string): Promise<void> {
    await this.ui.addGroup(groupId);
  }

  async expectGroupIsVisible(groupId: string): Promise<void> {
    expect(await this.ui.visibleGroupIds()).toContain(groupId);
  }

  async expectEmptyGroupIsStaged(groupId: string): Promise<void> {
    expect(await this.ui.selectedGroupId()).toBe(groupId);
    expect(await this.ui.persistedPermissionSet(groupId)).toEqual({ groupId, connectorIds: [], capabilities: [] });
    expect(await this.ui.hasUnsavedChanges()).toBe(false);
  }

  async expectDistinctGroupValues(firstGroupId: string, secondGroupId: string): Promise<void> {
    expect(await this.ui.visibleGroupIds()).toEqual(expect.arrayContaining([firstGroupId, secondGroupId]));
    expect(firstGroupId).not.toBe(secondGroupId);
  }

  async expectEmptyGroupValidation(): Promise<void> {
    await this.ui.addGroup('');
    expect(await this.ui.visibleValidationMessage()).toContain('Group value is required');
  }
}

class AdminGroupPermissionsGuidanceDsl {
  constructor(private readonly ui: GroupPermissionsGuidanceUi) {}

  async expectExactMatchGuidance(): Promise<void> {
    expect(await this.ui.visibleExactMatchGuidance()).toContain('exactly match');
  }
}

class AdminGroupPermissionsAssignableTargetsDsl {
  constructor(private readonly ui: GroupPermissionsAssignableTargetsUi) {}

  async expectOnlyAssignableTargetsAreVisible(): Promise<void> {
    expect(await this.ui.visibleAssignableConnectorIds()).toEqual(['gmail', 'slack']);
    expect(await this.ui.visibleAssignableTools()).toEqual([
      { connectorId: 'gmail', operationName: 'email.read' },
      { connectorId: 'gmail', operationName: 'email.send' },
      { connectorId: 'slack', operationName: 'slack.read' }
    ]);
  }
}

class AdminGroupPermissionsEditorDsl {
  constructor(private readonly ui: GroupPermissionsGroupSelectionUi & GroupPermissionsEditorUi & GroupPermissionsSaveUi) {}

  async loadGroup(groupId: string): Promise<void> {
    await this.ui.selectGroup(groupId);
  }

  async stageToolPermission(groupId: string, connectorId: string, operationName: string): Promise<void> {
    await this.ui.selectGroup(groupId);
    await this.ui.grantConnector(connectorId);
    await this.ui.grantTool({ connectorId, operationName });
  }

  async expectPermissionIsOnlyStaged(groupId: string, connectorId: string, operationName: string): Promise<void> {
    expect(await this.ui.stagedPermissionSet()).toEqual({ groupId, connectorIds: [connectorId], capabilities: [{ connectorId, kind: 'tool', key: operationName }] });
    expect(await this.ui.persistedPermissionSet(groupId)).not.toEqual(await this.ui.stagedPermissionSet());
  }

  async expectSavedPermission(groupId: string, connectorId: string, operationName: string): Promise<void> {
    expect(await this.ui.persistedPermissionSet(groupId)).toEqual({ groupId, connectorIds: [connectorId], capabilities: [{ connectorId, kind: 'tool', key: operationName }] });
    expect(await this.ui.hasUnsavedChanges()).toBe(false);
  }

  async replaceSupportPermissions(): Promise<void> {
    await this.ui.selectGroup('support');
    await this.ui.revokeTool({ connectorId: 'slack', operationName: 'slack.read' });
    await this.ui.grantConnector('gmail');
    await this.ui.grantTool({ connectorId: 'gmail', operationName: 'email.read' });
    await this.ui.saveSelectedGroupPermissions();
  }

  async expectSupportPermissionsWereReplaced(): Promise<void> {
    expect(await this.ui.persistedPermissionSet('support')).toEqual({
      groupId: 'support',
      connectorIds: ['gmail'],
      capabilities: [{ connectorId: 'gmail', kind: 'tool', key: 'email.read' }]
    });
  }
}

class AdminGroupPermissionsSaveDsl {
  constructor(private readonly ui: GroupPermissionsGroupListUi & GroupPermissionsGroupAdditionUi & GroupPermissionsEditorUi & GroupPermissionsSaveUi) {}

  async saveSelectedGroup(): Promise<SaveGroupPermissionsResult> {
    return await this.ui.saveSelectedGroupPermissions();
  }

  async saveEmptyGroup(groupId: string): Promise<void> {
    await this.ui.addGroup(groupId);
  }

  async expectSavedEmptyGroup(groupId: string): Promise<void> {
    expect(await this.ui.visibleGroupIds()).toContain(groupId);
    expect(await this.ui.persistedPermissionSet(groupId)).toEqual({ groupId, connectorIds: [], capabilities: [] });
  }

  async expectUnknownTargetSaveIsRejected(): Promise<void> {
    const result = await this.ui.saveSelectedGroupPermissions();
    expect(result.status).toBe('rejected');
    expect(await this.ui.visibleSaveMessage()).toContain('not available');
    expect(await this.ui.hasUnsavedChanges()).toBe(true);
  }

  async expectFailedSavePreservesStagedChanges(): Promise<void> {
    const stagedBeforeSave = await this.ui.stagedPermissionSet();
    const result = await this.ui.saveSelectedGroupPermissions();
    expect(result.status).toBe('failed');
    expect(await this.ui.stagedPermissionSet()).toEqual(stagedBeforeSave);
    expect(await this.ui.hasUnsavedChanges()).toBe(true);
  }
}

class AdminGroupPermissionsUnsavedDsl {
  constructor(private readonly ui: GroupPermissionsGroupSelectionUi & GroupPermissionsEditorUi & GroupPermissionsUnsavedChangesUi & GroupPermissionsNavigationUi) {}

  async trySwitchGroupAndCancel(targetGroupId: string): Promise<void> {
    await this.ui.attemptSelectGroupWithUnsavedChanges(targetGroupId);
    expect(await this.ui.visibleUnsavedChangesWarning()).toContain('unsaved');
    await this.ui.resolveUnsavedChangesWarning('cancel');
  }

  async expectStillEditing(groupId: string): Promise<void> {
    expect(await this.ui.selectedGroupId()).toBe(groupId);
    expect(await this.ui.hasUnsavedChanges()).toBe(true);
  }

  async trySwitchGroupAndDiscard(targetGroupId: string): Promise<void> {
    await this.ui.attemptSelectGroupWithUnsavedChanges(targetGroupId);
    expect(await this.ui.visibleUnsavedChangesWarning()).toContain('unsaved');
    await this.ui.resolveUnsavedChangesWarning('discard');
  }

  async expectSelectedGroup(groupId: string): Promise<void> {
    expect(await this.ui.selectedGroupId()).toBe(groupId);
  }

  async discardChangesAndReload(): Promise<void> {
    await this.ui.resolveUnsavedChangesWarning('discard');
    await this.ui.reloadGroupPermissionsTab();
  }
}

class AdminGroupPermissionsRuntimeDsl {
  constructor(private readonly runtime: GroupPermissionRuntimeProbe) {}

  async expectRuntimeAccessForExactGroup(jwtGroup: string, toolName: string): Promise<void> {
    expect(await this.runtime.visibleToolNamesForJwtGroups([jwtGroup])).toContain(toolName);
  }

  async expectRuntimeDoesNotGrantSimilarGroup(jwtGroup: string, toolName: string): Promise<void> {
    expect(await this.runtime.visibleToolNamesForJwtGroups([jwtGroup])).not.toContain(toolName);
  }
}

class AdminGroupPermissionsAuthorizationDsl {
  constructor(private readonly authorization: GroupPermissionAuthorization) {}

  async expectGroupPermissionsAreUnavailableToNonAdmin(): Promise<void> {
    expect(await this.authorization.canOpenGroupPermissionsAdmin()).toBe(false);
  }
}

class SvelteKitGroupPermissionsDriverState {
  pageData: Record<string, unknown> = {};
  selectedGroup: string | null = null;
  saveMessage: string | null = null;
  private readonly detailCache = new Map<string, GroupPermissionSet>();
  private targetsLoaded = false;

  constructor(readonly fetch: typeof globalThis.fetch) {}

  async stateModule(): Promise<GroupPermissionsStateModule> {
    return (await import('$lib/components/admin/group-permissions/group-permissions-state.svelte')) as never;
  }

  async loadSelection(groupId: string): Promise<void> {
    const domain = await import('$lib/admin/group-permissions');
    let detail = this.detailCache.get(groupId);
    if (detail === undefined) {
      const response = await this.fetch(`http://api:8000/admin/mcp-permissions/groups/${encodeURIComponent(groupId)}`);
      detail = domain.mapGroupPermissionSet(domain.apiGroupPermissionSetSchema.parse(await response.json()));
      this.detailCache.set(groupId, detail);
    }
    if (!this.targetsLoaded) {
      const response = await this.fetch('http://api:8000/admin/mcp-permissions/assignable-targets');
      this.pageData = {
        ...this.pageData,
        connectors: domain.mapAssignableTargets(domain.apiAssignableTargetsResponseSchema.parse(await response.json()))
      };
      this.targetsLoaded = true;
    }
    const groups = (this.pageData.groups as Array<{ groupId: string }> | undefined) ?? [];
    this.pageData = { ...this.pageData, groups: groups.map((group) => group.groupId === groupId ? detail : group) };
    this.selectedGroup = groupId;
  }

  invalidateDetail(groupId: string): void {
    this.detailCache.delete(groupId);
  }

  requireSelectedGroup(): string {
    if (this.selectedGroup === null) {
      throw new Error('No group selected');
    }
    return this.selectedGroup;
  }
}

class SvelteKitGroupPermissionsNavigationDriver implements GroupPermissionsNavigationUi {
  constructor(private readonly state: SvelteKitGroupPermissionsDriverState) {}

  async openGroupPermissionsTab(): Promise<void> {
    const { load } = (await import('../../routes/admin/group-permissions/+page.server')) as unknown as { load: GroupPermissionsPageLoad };
    this.state.pageData = (await load({ fetch: this.state.fetch, url: new URL('http://frontend/admin/group-permissions') })) as Record<string, unknown>;
  }

  async reloadGroupPermissionsTab(): Promise<void> {
    await this.openGroupPermissionsTab();
  }

  async visibleNavigationLabels(): Promise<string[]> {
    const { load } = (await import('../../routes/admin/+page')) as unknown as { load: () => Promise<unknown> | unknown };
    const pageData = (await load()) as { navigationItems: Array<{ label: string }> };
    return pageData.navigationItems.map((item) => item.label);
  }
}

class SvelteKitGroupPermissionsListDriver implements GroupPermissionsListUi {
  constructor(private readonly state: SvelteKitGroupPermissionsDriverState) {}

  async visibleGroupIds(): Promise<string[]> {
    return ((this.state.pageData.groups as Array<{ groupId: string }> | undefined) ?? []).map((group) => group.groupId);
  }

  async selectedGroupId(): Promise<string | null> {
    return this.state.selectedGroup;
  }

  async selectGroup(groupId: string): Promise<void> {
    await this.state.loadSelection(groupId);
  }

  async addGroup(groupId: string): Promise<void> {
    const { actions } = (await import('../../routes/admin/group-permissions/+page.server')) as unknown as { actions: GroupPermissionsPageActions };
    const response = (await actions.registerPermissionGroup({ fetch: this.state.fetch, request: this.createRegisterRequest(groupId) })) as SaveGroupPermissionsResult;
    if (response.status === 'rejected') {
      this.state.pageData = { ...this.state.pageData, validationMessage: response.message };
      return;
    }

    await this.reloadAfterRegister(groupId, response.status);
  }

  private createRegisterRequest(groupId: string): Request {
    const body = new FormData();
    body.set('groupId', groupId);
    return new Request('http://frontend/admin/group-permissions', { method: 'POST', body });
  }

  private async reloadAfterRegister(groupId: string, status: string): Promise<void> {
    if (status !== 'registered') {
      return;
    }

    const { load } = (await import('../../routes/admin/group-permissions/+page.server')) as unknown as { load: GroupPermissionsPageLoad };
    this.state.pageData = (await load({ fetch: this.state.fetch, url: new URL('http://frontend/admin/group-permissions') })) as Record<string, unknown>;
    await this.state.loadSelection(groupId);
  }

  async visibleValidationMessage(): Promise<string | null> {
    return (this.state.pageData.validationMessage as string | undefined) ?? null;
  }
}

class SvelteKitGroupPermissionsGuidanceDriver implements GroupPermissionsGuidanceUi {
  constructor(private readonly state: SvelteKitGroupPermissionsDriverState) {}

  async visibleExactMatchGuidance(): Promise<string> {
    return (this.state.pageData.exactMatchGuidance as string | undefined) ?? '';
  }
}

class SvelteKitGroupPermissionsAssignableTargetsDriver implements GroupPermissionsAssignableTargetsUi {
  constructor(private readonly state: SvelteKitGroupPermissionsDriverState) {}

  async visibleAssignableConnectorIds(): Promise<string[]> {
    return ((this.state.pageData.connectors as Array<{ id: string }> | undefined) ?? []).map((connector) => connector.id);
  }

  async visibleAssignableTools(): Promise<GroupPermissionToolRef[]> {
    return ((this.state.pageData.connectors as Array<{ id: string; capabilities: Array<{ kind: string; key: string }> }> | undefined) ?? []).flatMap((connector) =>
      connector.capabilities
        .filter((capability) => capability.kind === 'tool')
        .map((capability) => ({ connectorId: connector.id, operationName: capability.key }))
    );
  }
}

class SvelteKitGroupPermissionsEditorDriver implements GroupPermissionsEditorUi {
  constructor(private readonly state: SvelteKitGroupPermissionsDriverState) {}

  async grantConnector(connectorId: string): Promise<void> {
    await this.updateStagedPermission({ connectorId });
  }

  async revokeConnector(connectorId: string): Promise<void> {
    const module = await this.state.stateModule();
    this.state.pageData = module.revokeConnectorFromState(this.state.pageData, this.state.requireSelectedGroup(), connectorId);
  }

  async grantTool(tool: GroupPermissionToolRef): Promise<void> {
    await this.updateStagedPermission(tool);
  }

  async revokeTool(tool: GroupPermissionToolRef): Promise<void> {
    const module = await this.state.stateModule();
    this.state.pageData = module.revokeToolFromState(this.state.pageData, this.state.requireSelectedGroup(), tool);
  }

  async stagedPermissionSet(): Promise<GroupPermissionSet | null> {
    const module = await this.state.stateModule();
    return module.stagedPermissionSetFromState(this.state.pageData, this.state.requireSelectedGroup());
  }

  async persistedPermissionSet(groupId: string): Promise<GroupPermissionSet | null> {
    const module = await this.state.stateModule();
    return module.persistedPermissionSetFromState(this.state.pageData, groupId);
  }

  async hasUnsavedChanges(): Promise<boolean> {
    const module = await this.state.stateModule();
    return module.hasUnsavedChangesInState(this.state.pageData, this.state.requireSelectedGroup());
  }

  private async updateStagedPermission(tool: { connectorId: string; operationName?: string }): Promise<void> {
    const module = await this.state.stateModule();
    this.state.pageData = module.grantPermissionInState(
      this.state.pageData,
      this.state.requireSelectedGroup(),
      tool.operationName === undefined
        ? { connectorId: tool.connectorId }
        : { connectorId: tool.connectorId, kind: 'tool', key: tool.operationName }
    );
  }
}

class SvelteKitGroupPermissionsSaveDriver implements GroupPermissionsSaveUi {
  constructor(
    private readonly state: SvelteKitGroupPermissionsDriverState,
    private readonly navigation: GroupPermissionsNavigationUi
  ) {}

  async saveSelectedGroupPermissions(): Promise<SaveGroupPermissionsResult> {
    const { actions } = (await import('../../routes/admin/group-permissions/+page.server')) as unknown as { actions: GroupPermissionsPageActions };
    const response = (await actions.saveGroupPermissions({ fetch: this.state.fetch, request: await this.createSaveRequest() })) as SaveGroupPermissionsResult;
    this.state.saveMessage = response.status === 'saved' ? 'Permissions saved' : 'message' in response ? response.message : null;
    if (response.status === 'saved') {
      const groupId = this.state.requireSelectedGroup();
      this.state.invalidateDetail(groupId);
      await this.navigation.reloadGroupPermissionsTab();
      await this.state.loadSelection(groupId);
    }
    return response;
  }

  async visibleSaveMessage(): Promise<string | null> {
    return this.state.saveMessage;
  }

  private async createSaveRequest(): Promise<Request> {
    const groupId = this.state.requireSelectedGroup();
    const module = await this.state.stateModule();
    const draft = module.stagedPermissionSetFromState(this.state.pageData, groupId);
    const persisted = module.persistedPermissionSetFromState(this.state.pageData, groupId) ?? { groupId, connectorIds: [], capabilities: [] };
    const { permissionSetDifference } = await import('$lib/admin/group-permissions');
    const body = new FormData();
    body.set('groupId', groupId);
    body.set('permissionSet', JSON.stringify(permissionSetDifference(persisted, draft ?? persisted)));
    return new Request('http://frontend/admin/group-permissions', { method: 'POST', body });
  }
}

class SvelteKitGroupPermissionsUnsavedDriver implements GroupPermissionsUnsavedChangesUi {
  constructor(private readonly state: SvelteKitGroupPermissionsDriverState) {}

  async attemptSelectGroupWithUnsavedChanges(groupId: string): Promise<void> {
    const module = await this.state.stateModule();
    this.state.pageData = module.stageGroupSelectionWithUnsavedChanges(this.state.pageData, groupId);
  }

  async visibleUnsavedChangesWarning(): Promise<string | null> {
    return (this.state.pageData.unsavedChangesWarning as string | undefined) ?? null;
  }

  async resolveUnsavedChangesWarning(decision: UnsavedChangesDecision): Promise<void> {
    const module = await this.state.stateModule();
    const result = module.resolveUnsavedChangesInState(this.state.pageData, decision);
    this.state.pageData = result.pageData;
    this.state.selectedGroup = result.selectedGroupId;
    if (decision === 'discard' && result.selectedGroupId !== null) {
      await this.state.loadSelection(result.selectedGroupId);
    }
  }
}

type SvelteKitAdminGroupPermissionsDriverParts = {
  navigation: SvelteKitGroupPermissionsNavigationDriver;
  list: SvelteKitGroupPermissionsListDriver;
  guidance: SvelteKitGroupPermissionsGuidanceDriver;
  targets: SvelteKitGroupPermissionsAssignableTargetsDriver;
  editor: SvelteKitGroupPermissionsEditorDriver;
  save: SvelteKitGroupPermissionsSaveDriver;
  unsaved: SvelteKitGroupPermissionsUnsavedDriver;
};

function createSvelteKitAdminGroupPermissionsDriver(fetch: typeof globalThis.fetch): AdminGroupPermissionsUi {
  const state = new SvelteKitGroupPermissionsDriverState(fetch);
  const navigation = new SvelteKitGroupPermissionsNavigationDriver(state);
  return createSvelteKitAdminGroupPermissionsUi({
    navigation,
    list: new SvelteKitGroupPermissionsListDriver(state),
    guidance: new SvelteKitGroupPermissionsGuidanceDriver(state),
    targets: new SvelteKitGroupPermissionsAssignableTargetsDriver(state),
    editor: new SvelteKitGroupPermissionsEditorDriver(state),
    save: new SvelteKitGroupPermissionsSaveDriver(state, navigation),
    unsaved: new SvelteKitGroupPermissionsUnsavedDriver(state)
  });
}

function createSvelteKitAdminGroupPermissionsUi(parts: SvelteKitAdminGroupPermissionsDriverParts): AdminGroupPermissionsUi {
  return {
    ...createSvelteKitNavigationUi(parts.navigation),
    ...createSvelteKitListUi(parts.list),
    visibleExactMatchGuidance: () => parts.guidance.visibleExactMatchGuidance(),
    visibleAssignableConnectorIds: () => parts.targets.visibleAssignableConnectorIds(),
    visibleAssignableTools: () => parts.targets.visibleAssignableTools(),
    ...createSvelteKitEditorUi(parts.editor),
    saveSelectedGroupPermissions: () => parts.save.saveSelectedGroupPermissions(),
    visibleSaveMessage: () => parts.save.visibleSaveMessage(),
    ...createSvelteKitUnsavedUi(parts.unsaved)
  };
}

function createSvelteKitNavigationUi(navigation: SvelteKitGroupPermissionsNavigationDriver): GroupPermissionsNavigationUi {
  return {
    openGroupPermissionsTab: () => navigation.openGroupPermissionsTab(),
    reloadGroupPermissionsTab: () => navigation.reloadGroupPermissionsTab(),
    visibleNavigationLabels: () => navigation.visibleNavigationLabels()
  };
}

function createSvelteKitListUi(list: SvelteKitGroupPermissionsListDriver): GroupPermissionsListUi {
  return {
    visibleGroupIds: () => list.visibleGroupIds(),
    selectedGroupId: () => list.selectedGroupId(),
    selectGroup: (groupId: string) => list.selectGroup(groupId),
    addGroup: (groupId: string) => list.addGroup(groupId),
    visibleValidationMessage: () => list.visibleValidationMessage()
  };
}

function createSvelteKitEditorUi(editor: SvelteKitGroupPermissionsEditorDriver): GroupPermissionsEditorUi {
  return {
    grantConnector: (connectorId: string) => editor.grantConnector(connectorId),
    revokeConnector: (connectorId: string) => editor.revokeConnector(connectorId),
    grantTool: (tool: GroupPermissionToolRef) => editor.grantTool(tool),
    revokeTool: (tool: GroupPermissionToolRef) => editor.revokeTool(tool),
    stagedPermissionSet: () => editor.stagedPermissionSet(),
    persistedPermissionSet: (groupId: string) => editor.persistedPermissionSet(groupId),
    hasUnsavedChanges: () => editor.hasUnsavedChanges()
  };
}

function createSvelteKitUnsavedUi(unsaved: SvelteKitGroupPermissionsUnsavedDriver): GroupPermissionsUnsavedChangesUi {
  return {
    attemptSelectGroupWithUnsavedChanges: (groupId: string) => unsaved.attemptSelectGroupWithUnsavedChanges(groupId),
    visibleUnsavedChangesWarning: () => unsaved.visibleUnsavedChangesWarning(),
    resolveUnsavedChangesWarning: (decision: UnsavedChangesDecision) => unsaved.resolveUnsavedChangesWarning(decision)
  };
}

class HttpGroupPermissionAuthorization implements GroupPermissionAuthorization {
  constructor(private readonly fetch: typeof globalThis.fetch) {}

  async canOpenGroupPermissionsAdmin(): Promise<boolean> {
    const response = await this.fetch('http://api:8000/admin/mcp-permissions/groups');
    return response.status !== 401 && response.status !== 403;
  }
}

class HttpGroupPermissionRuntimeProbe implements GroupPermissionRuntimeProbe {
  constructor(private readonly fetch: typeof globalThis.fetch) {}

  async visibleToolNamesForJwtGroups(jwtGroups: string[]): Promise<string[]> {
    const response = await this.fetch('http://api:8000/mcp/tools/visible-for-groups', {
      method: 'POST',
      body: JSON.stringify({ groups: jwtGroups })
    });
    const body = (await response.json()) as { toolNames: string[] };
    return body.toolNames;
  }
}

function createJsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

async function parseJsonRequestBody<T>(input: RequestInfo | URL, init: RequestInit | undefined, fallback: T): Promise<T> {
  if (input instanceof Request) {
    return (await input.json()) as T;
  }

  if (typeof init?.body === 'string') {
    return JSON.parse(init.body) as T;
  }

  return fallback;
}

type GroupPermissionsFetchOptions = {
  saveStatus?: number;
  saveBody?: unknown;
};

type SaveGroupPermissionsRequestBody = {
  connectors: Array<{ connector_id: string; permission_status: 'enabled' | 'disabled' }>;
  capabilities: Array<{
    connector_id: string;
    capability_kind: 'tool' | 'prompt' | 'resource' | 'resource_template';
    capability_key: string;
    permission_status: 'enabled' | 'disabled';
  }>;
};

type SaveGroupPermissionSetRequest = {
  input: RequestInfo | URL;
  init: RequestInit | undefined;
  url: string;
  groups: GroupPermissionSet[];
  options: GroupPermissionsFetchOptions;
};

function createInitialGroupPermissionSets(): GroupPermissionSet[] {
  return [
    { groupId: 'engineering', connectorIds: [], capabilities: [] },
    { groupId: 'support', connectorIds: ['slack'], capabilities: [{ connectorId: 'slack', kind: 'tool', key: 'slack.read' }] }
  ];
}

function extractGroupIdFromPermissionsUrl(url: string): string {
  return decodeURIComponent(url.split('/admin/mcp-permissions/groups/')[1] ?? '');
}

function createAssignableTargetsResponse(): Response {
  return createJsonResponse({
    connectors: [
      { connector_id: 'gmail', display_name: 'Gmail', description: 'Read and send email' },
      { connector_id: 'slack', display_name: 'Slack', description: 'Read Slack channels' }
    ],
    capabilities: [
      { connector_id: 'gmail', capability_kind: 'tool', capability_key: 'email.read', display_name: 'Read email', description: 'Read inbox' },
      { connector_id: 'gmail', capability_kind: 'tool', capability_key: 'email.send', display_name: 'Send email', description: 'Send mail' },
      { connector_id: 'slack', capability_kind: 'tool', capability_key: 'slack.read', display_name: 'Read Slack', description: 'Read channels' }
    ]
  });
}

function createGroupPermissionsResponse(groups: GroupPermissionSet[]): Response {
  return createJsonResponse({ groups: groups.map((group) => ({ group_id: group.groupId })) });
}

function createGroupPermissionDetailResponse(url: string, groups: GroupPermissionSet[]): Response {
  const groupId = extractGroupIdFromPermissionsUrl(url);
  const group = groups.find((candidate) => candidate.groupId === groupId);
  if (group === undefined) return createJsonResponse({ detail: 'Not found' }, 404);
  return createJsonResponse({
    group_id: group.groupId,
    connector_ids: group.connectorIds,
    capabilities: group.capabilities.map((capability) => ({
      connector_id: capability.connectorId,
      capability_kind: capability.kind,
      capability_key: capability.key
    }))
  });
}

function registerGroupPermissionSet(url: string, groups: GroupPermissionSet[]): Response {
  const groupId = extractGroupIdFromPermissionsUrl(url);
  if (groupId.trim() === '') {
    return createJsonResponse({ detail: 'Group value is required' }, 400);
  }

  if (!groups.some((group) => group.groupId === groupId)) {
    groups.push({ groupId, connectorIds: [], capabilities: [] });
  }
  return createJsonResponse({ status: 'applied', group_id: groupId });
}

async function createVisibleToolsResponse(input: RequestInfo | URL, init: RequestInit | undefined, groups: GroupPermissionSet[]): Promise<Response> {
  const requestBody = await parseJsonRequestBody(input, init, { groups: [] } as { groups: string[] });
  const visibleTools = groups
    .filter((group) => requestBody.groups.includes(group.groupId))
    .flatMap((group) =>
      group.capabilities
        .filter((capability) => capability.kind === 'tool')
        .map((capability) => `${capability.connectorId}_${capability.key}`)
    );
  return createJsonResponse({ toolNames: visibleTools });
}

async function saveGroupPermissionSet(request: SaveGroupPermissionSetRequest): Promise<Response> {
  const groupId = extractGroupIdFromPermissionsUrl(request.url).replace(/\/permissions$/, '');
  const status = request.options.saveStatus ?? 200;
  if (status >= 200 && status < 300) {
    const requestBody = await parseJsonRequestBody(request.input, request.init, { connectors: [], capabilities: [] } as SaveGroupPermissionsRequestBody);
    const permissionSet = request.groups.find((group) => group.groupId === groupId);
    if (permissionSet !== undefined) {
      for (const connector of requestBody.connectors) {
        permissionSet.connectorIds = connector.permission_status === 'enabled'
          ? [...new Set([...permissionSet.connectorIds, connector.connector_id])]
          : permissionSet.connectorIds.filter((connectorId) => connectorId !== connector.connector_id);
      }
      for (const capability of requestBody.capabilities) {
        permissionSet.capabilities = permissionSet.capabilities.filter(
          (existing) =>
            existing.connectorId !== capability.connector_id ||
            existing.kind !== capability.capability_kind ||
            existing.key !== capability.capability_key
        );
        if (capability.permission_status === 'enabled') {
          permissionSet.capabilities.push({
            connectorId: capability.connector_id,
            kind: capability.capability_kind,
            key: capability.capability_key
          });
        }
      }
    }
  }
  return createJsonResponse(request.options.saveBody ?? { status: 'saved', group_id: groupId }, status);
}

function createGroupPermissionsFetch(options: GroupPermissionsFetchOptions = {}): typeof fetch {
  const groups = createInitialGroupPermissionSets();

  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    const method = input instanceof Request ? input.method : (init?.method ?? 'GET');

    if (url === 'http://api:8000/admin/mcp-permissions/assignable-targets') {
      return createAssignableTargetsResponse();
    }

    if (url === 'http://api:8000/admin/mcp-permissions/groups') {
      return createGroupPermissionsResponse(groups);
    }

    if (url.includes('/admin/mcp-permissions/groups/') && method === 'GET') {
      return createGroupPermissionDetailResponse(url, groups);
    }

    if (url.includes('/admin/mcp-permissions/groups/') && method === 'POST') {
      return registerGroupPermissionSet(url, groups);
    }

    if (url === 'http://api:8000/mcp/tools/visible-for-groups') {
      return createVisibleToolsResponse(input, init, groups);
    }

    if (url.includes('/admin/mcp-permissions/groups/') && url.endsWith('/permissions') && method === 'PUT') {
      return saveGroupPermissionSet({ input, init, url, groups, options });
    }

    return new Response('Not found', { status: 404 });
  }) as typeof fetch;
}

function createAcceptanceDsl(fetch = createGroupPermissionsFetch()): AdminGroupPermissionsDsl {
  return new AdminGroupPermissionsDsl(
    createSvelteKitAdminGroupPermissionsDriver(fetch),
    new HttpGroupPermissionRuntimeProbe(fetch),
    new HttpGroupPermissionAuthorization(fetch)
  );
}

describe('admin group permissions UI acceptance', () => {
  test('admin opens with summaries and the first group editor preloaded without hydration requests', async () => {
    const fetch = createGroupPermissionsFetch();
    const dsl = createAcceptanceDsl(fetch);

    await dsl.navigation.openGroupPermissions();

    const requestedUrls = vi.mocked(fetch).mock.calls.map(([input]) => input instanceof Request ? input.url : String(input));
    expect(requestedUrls).toEqual([
      'http://api:8000/admin/mcp-permissions/groups',
      'http://api:8000/admin/mcp-permissions/groups/engineering',
      'http://api:8000/admin/mcp-permissions/assignable-targets'
    ]);
    await dsl.navigation.expectGroupPermissionsNavigation();
    await dsl.list.expectExistingGroups(['engineering', 'support']);
    await dsl.guidance.expectExactMatchGuidance();
  });

  test('registered groups appear in the sidebar when SvelteKit refreshes the page data', async () => {
    const fetch = createGroupPermissionsFetch();
    const { load, actions } = (await import('../../routes/admin/group-permissions/+page.server')) as unknown as {
      load: GroupPermissionsPageLoad;
      actions: GroupPermissionsPageActions;
    };
    const { GroupPermissionsState } = await import('$lib/components/admin/group-permissions/group-permissions-state.svelte');
    const initialData = (await load({ fetch, url: new URL('http://frontend/admin/group-permissions') })) as ConstructorParameters<
      typeof GroupPermissionsState
    >[0];
    const sidebarState = new GroupPermissionsState(initialData, null, null);
    const body = new FormData();
    body.set('groupId', 'engineering-managers');

    await actions.registerPermissionGroup({
      fetch,
      request: new Request('http://frontend/admin/group-permissions', { method: 'POST', body })
    });
    const refreshedData = (await load({ fetch, url: new URL('http://frontend/admin/group-permissions') })) as typeof initialData;
    sidebarState.synchronizeServerData(refreshedData, 'Registered group engineering-managers', 'engineering-managers');

    expect(refreshedData.groups.map((group) => group.groupId)).toContain('engineering-managers');
    expect(sidebarState.groups.map((group) => group.groupId)).toContain('engineering-managers');
  });

  test('admin manually adds a new group as an unsaved empty permission set', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.list.addGroup('engineering-managers');

    await dsl.list.expectGroupIsVisible('engineering-managers');
    await dsl.list.expectEmptyGroupIsStaged('engineering-managers');
  });

  test('admin only sees permission targets returned by assignable targets', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.loadGroup('engineering');

    await dsl.targets.expectOnlyAssignableTargetsAreVisible();
  });

  test('admin stages connector and tool permissions before saving', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'gmail', 'email.read');

    await dsl.editor.expectPermissionIsOnlyStaged('engineering', 'gmail', 'email.read');
  });

  test('admin saves staged group permissions and exact JWT group receives access', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'gmail', 'email.read');
    await dsl.save.saveSelectedGroup();

    await dsl.editor.expectSavedPermission('engineering', 'gmail', 'email.read');
    await dsl.runtime.expectRuntimeAccessForExactGroup('engineering', 'gmail_email.read');
  });

  test('admin replaces existing group permissions in one explicit save', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.replaceSupportPermissions();

    await dsl.editor.expectSupportPermissionsWereReplaced();
  });

  test('saved empty groups remain visible for later configuration', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.save.saveEmptyGroup('future-team');

    await dsl.save.expectSavedEmptyGroup('future-team');
  });

  test('similar group values are distinct and exact matching is explained', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.list.addGroup('Engineering');

    await dsl.list.expectDistinctGroupValues('Engineering', 'engineering');
    await dsl.guidance.expectExactMatchGuidance();
  });

  test('admin can cancel an unsaved group switch and keep staged changes', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'gmail', 'email.read');
    await dsl.unsaved.trySwitchGroupAndCancel('support');

    await dsl.unsaved.expectStillEditing('engineering');
  });

  test('admin can discard staged changes when switching groups', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'gmail', 'email.read');
    await dsl.unsaved.trySwitchGroupAndDiscard('support');

    await dsl.unsaved.expectSelectedGroup('support');
  });

  test('save rejection for an unavailable permission target keeps staged changes', async () => {
    const dsl = createAcceptanceDsl(
      createGroupPermissionsFetch({ saveStatus: 404, saveBody: { status: 'rejected', group_id: 'engineering', message: 'Permission target is not available' } })
    );

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'unknown', 'missing.operation');

    await dsl.save.expectUnknownTargetSaveIsRejected();
  });

  test('empty group values are rejected before a group is added', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();

    await dsl.list.expectEmptyGroupValidation();
  });

  test('save failure preserves staged changes', async () => {
    const dsl = createAcceptanceDsl(
      createGroupPermissionsFetch({ saveStatus: 503, saveBody: { status: 'failed', group_id: 'engineering', message: 'Permissions could not be saved' } })
    );

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'gmail', 'email.read');

    await dsl.save.expectFailedSavePreservesStagedChanges();
  });

  test('non-admin users cannot access group permission management', async () => {
    const dsl = createAcceptanceDsl(vi.fn(async () => new Response('Forbidden', { status: 403 })) as typeof fetch);

    await dsl.auth.expectGroupPermissionsAreUnavailableToNonAdmin();
  });

  test('similar JWT group values do not receive access from another group configuration', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'gmail', 'email.read');
    await dsl.save.saveSelectedGroup();

    await dsl.runtime.expectRuntimeDoesNotGrantSimilarGroup('engineering-team', 'gmail_email.read');
  });

  test('saved changes are visible after reload', async () => {
    const dsl = createAcceptanceDsl();

    await dsl.navigation.openGroupPermissions();
    await dsl.editor.stageToolPermission('engineering', 'gmail', 'email.read');
    await dsl.save.saveSelectedGroup();
    await dsl.navigation.reloadGroupPermissions();
    await dsl.editor.loadGroup('engineering');

    await dsl.editor.expectSavedPermission('engineering', 'gmail', 'email.read');
  });
});
