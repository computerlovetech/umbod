import { exactMatchGuidance, mapGroupPermissionSummary, type GroupPermissionsInitialTarget } from '$lib/admin/group-permissions';
import type { CatalogueGroup } from '$lib/admin/groups/domain/schemas';
import type { GroupCatalogue } from '$lib/admin/groups/port';
import type { FilesystemAdministration } from '$lib/admin/filesystem/port';
import { FilesystemAccessState, type FilesystemGroup } from '../filesystem/filesystem-access-state.svelte';
import { FilesystemGroupEditorState } from '../filesystem/filesystem-group-editor-state.svelte';
import { GroupPermissionsState } from './group-permissions-state.svelte';
import type { GroupPermissionsLoader } from './group-permissions-loader';
import type { GroupPermissionsSaver } from './group-permissions-saver';
import type { GroupPermissionsTab } from './group-permissions-route-state.svelte';

type WorkspaceGroup = Readonly<Omit<FilesystemGroup, 'permissions'> & { permissions: Readonly<FilesystemGroup['permissions']> }>;

export class GroupPermissionsWorkspaceState {
  readonly filesystem: FilesystemAccessState;
  readonly filesystemEditor: FilesystemGroupEditorState;
  private connectorState = $state.raw<GroupPermissionsState | null>(null);
  private selection = $state<string | null>(null);
  private pending = $state<string | null>(null);
  private activeTab: GroupPermissionsTab = 'connectors';
  private disposed = false;
  private summaries = $derived.by(() => this.catalogue().map(mapGroupPermissionSummary));
  private entries = $derived.by(() => this.filesystem.groupEntries);

  constructor(
    private readonly catalogue: () => CatalogueGroup[],
    groups: GroupCatalogue,
    filesystem: FilesystemAdministration,
    private readonly loader: GroupPermissionsLoader,
    private readonly saver: GroupPermissionsSaver,
    private readonly target: () => GroupPermissionsInitialTarget | null
  ) {
    this.selection = catalogue()[0]?.group_id ?? null;
    this.filesystem = new FilesystemAccessState(filesystem, groups, catalogue);
    this.filesystemEditor = new FilesystemGroupEditorState(() => this.filesystem, () => this.selectedGroupId);
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
  get busy(): boolean { return this.connectorState?.saving === true || this.filesystem.saving; }
  get dirty(): boolean { return this.connectorState?.hasUnsavedChanges === true || this.filesystem.dirty; }

  activate = (tab: GroupPermissionsTab): void => {
    if (this.disposed) return;
    this.activeTab = tab;
    if (tab === 'filesystem') {
      void this.filesystem.ensureLoaded();
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
      }, null, this.selectedGroup?.registered ? this.selectedGroupId : null, this.loader, this.saver, this.target);
    }
    this.connectorState.synchronizeCatalogue(this.summaries);
    if (this.selectedGroup?.registered && this.selectedGroupId) this.connectorState.ensureSelection(this.selectedGroupId);
    this.connectorState.refreshRouteTarget();
  };

  requestSelection = (id: string): void => {
    if (this.disposed || this.busy || id === this.selectedGroupId || !this.groupEntries.some((group) => group.id === id)) return;
    if (this.connectorState?.hasUnsavedChanges && id !== this.connectorState.selectedGroupId) {
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
      this.commitSelection(id);
    }
  };

  private commitSelection(id: string): void {
    this.selection = id;
    if (this.activeTab === 'connectors') this.activate('connectors');
  }

  dispose = (): void => {
    this.disposed = true;
    this.connectorState?.dispose();
    this.filesystem.dispose();
  };
}
