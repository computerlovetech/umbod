import { exactMatchGuidance, mapGroupPermissionSummary, type GroupPermissionsInitialTarget } from '#lib/admin/group-permissions.js';
import type { CatalogueGroup } from '#lib/admin/groups/domain/schemas.js';
import type { NamespaceAdministration } from '#lib/admin/filesystem/namespaces-port.js';
import { NamespaceManagementState } from '../filesystem/namespace-management-state.svelte';
import { GroupPermissionsState } from './group-permissions-state.svelte';
import type { GroupPermissionsLoader } from './group-permissions-loader';
import type { GroupPermissionsSaver } from './group-permissions-saver';
import type { GroupPermissionsTab } from './group-permissions-route-state.svelte';

type WorkspaceGroup = Readonly<CatalogueGroup & { id: string }>;

export class GroupPermissionsWorkspaceState {
  readonly namespaces: NamespaceManagementState;
  private connectorState = $state.raw<GroupPermissionsState | null>(null);
  private selection = $state<string | null>(null);
  private pending = $state<string | null>(null);
  private activeTab: GroupPermissionsTab = 'connectors';
  private disposed = false;
  private summaries = $derived.by(() => this.catalogue().map(mapGroupPermissionSummary));
  private entries = $derived.by(() => this.catalogue().map((group) => ({ ...group, id: group.group_id })));

  constructor(
    private readonly catalogue: () => CatalogueGroup[],
    private readonly loader: GroupPermissionsLoader,
    private readonly saver: GroupPermissionsSaver,
    private readonly target: () => GroupPermissionsInitialTarget | null,
    namespaceAdministration: NamespaceAdministration,
    initialGroupId: string | null = null,
    private readonly onSelection?: (id: string) => void
  ) {
    const groups = catalogue();
    this.selection = groups.find((group) => group.group_id === initialGroupId)?.group_id ?? groups[0]?.group_id ?? null;
    this.namespaces = new NamespaceManagementState(namespaceAdministration, () => this.selectedGroupId);
  }

  get connectors(): GroupPermissionsState | null { return this.connectorState; }
  get groupEntries(): readonly WorkspaceGroup[] { return this.entries; }
  get selectedGroupId(): string | null {
    return this.groupEntries.some((group) => group.id === this.selection) ? this.selection : null;
  }
  get selectedGroup(): WorkspaceGroup | null {
    return this.groupEntries.find((group) => group.id === this.selectedGroupId) ?? null;
  }
  get pendingSelection(): string | null { return this.pending; }
  get busy(): boolean { return this.connectorState?.saving === true || this.namespaces.writing || this.namespaces.editorOpen || this.namespaces.confirmingDelete; }
  get dirty(): boolean { return this.connectorState?.hasUnsavedChanges === true || this.namespaces.hasUnsavedChanges; }

  activate = (tab: GroupPermissionsTab): void => {
    if (this.disposed) return;
    this.activeTab = tab;
    if (tab === 'filesystem') {
      void this.namespaces.ensureLoaded();
      return;
    }
    if (!this.connectorState) {
      this.connectorState = new GroupPermissionsState({
        groups: this.summaries,
        preloadedGroup: null,
        assignableTargets: [],
        exactMatchGuidance,
        initialTarget: null,
        originHref: null
      }, null, this.selectedGroupId, this.loader, this.saver, this.target);
    }
    this.connectorState.synchronizeCatalogue(this.summaries);
    if (this.selectedGroupId) this.connectorState.ensureSelection(this.selectedGroupId);
    this.connectorState.refreshRouteTarget();
  };

  requestSelection = (id: string): void => {
    if (this.disposed || this.busy || id === this.selectedGroupId || !this.groupEntries.some((group) => group.id === id)) return;
    if (this.dirty) {
      this.pending = id;
      return;
    }
    this.commitSelection(id);
  };

  resolveSelection = (decision: 'discard' | 'cancel'): void => {
    if (this.busy || this.disposed) return;
    const id = this.pending;
    this.pending = null;
    if (decision === 'discard' && id !== null && this.groupEntries.some((group) => group.id === id)) {
      this.connectorState?.discardSelectedDraft();
      this.namespaces.discardSelectedDraft();
      this.commitSelection(id);
    }
  };

  private commitSelection(id: string): void {
    this.selection = id;
    this.onSelection?.(id);
    if (this.activeTab === 'connectors') this.activate('connectors');
  }

  dispose = (): void => {
    this.disposed = true;
    this.connectorState?.dispose();
    this.namespaces.dispose();
  };
}
