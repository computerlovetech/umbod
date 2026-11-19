import type { FilePreviewState } from '../preview/file-preview-state.svelte';
import { NodeUpdateState } from './node-update-state.svelte';
import { DescriptionState } from './description-state.svelte';
import { SharingEligibilityState } from './sharing-eligibility-state.svelte';
import { SvelteMap } from 'svelte/reactivity';
import { FilesNavigationState } from './navigation-state.svelte';
import { RowDeletionState } from './row-deletion-state.svelte';
import { RowEditingState } from './row-editing-state.svelte';
import { DragMoveState } from './drag-move-state.svelte';
import { DeletionState } from './deletion-state.svelte';
import type { FilesApi } from '../api';
import { browseResultSchema, childrenSchema, filesystemNamespacesSchema, nodeIdSchema, type FilesystemNamespace, type NodeSummary } from '../domain/schemas';
import { readFailure, type FilesPhase } from '../errors';

const sharedWithMeParam = 'shared-with-me';
export const sharedWithMeHref = '/files?' + sharedWithMeParam;

export function filesHref(id?: string, sharedEntry: string | null = null): string {
  if (!id) return sharedEntry === null ? '/files' : sharedWithMeHref;
  const href = '/files?node=' + encodeURIComponent(id);
  return sharedEntry === null ? href : href + '&' + sharedWithMeParam + '=' + encodeURIComponent(sharedEntry);
}

export function filesTarget(url: URL): { node: string | null; sharedEntry: string | null } {
  return { node: url.searchParams.get('node'), sharedEntry: url.searchParams.get(sharedWithMeParam) };
}

export interface FilesLocation {
  readonly id: string;
  readonly label: string;
  readonly href: string;
  readonly selected: boolean;
}

export interface FilesLocationGroup {
  readonly kind: 'personal' | 'shared';
  readonly label: string;
  readonly locations: readonly FilesLocation[];
}

export class FilesState {
  private namespaceEntries = $state.raw<FilesystemNamespace[]>([]);
  get namespaces(): readonly FilesystemNamespace[] { return this.namespaceEntries; }
  private selectedNamespaceId = $state<string | undefined>(undefined);
  discoveryPhase = $state<FilesPhase>('loading');
  get selectedNamespace(): FilesystemNamespace | undefined { return this.namespaceEntries.find((entry) => entry.id === this.selectedNamespaceId); }
  readonly locationGroups: readonly FilesLocationGroup[] = $derived.by(() => {
    return (['personal', 'shared'] as const).flatMap((kind) => {
      const locations = this.namespaceEntries.filter((entry) => entry.kind === kind).map((entry) => ({
        id: entry.id,
        label: entry.kind === 'personal' ? 'My files' : entry.name,
        href: filesHref(entry.root_node_id),
        selected: entry.id === this.selectedNamespaceId
      }));
      return locations.length ? [{ kind, label: kind === 'personal' ? 'Personal' : 'Shared namespaces', locations }] : [];
    });
  });
  namespaceLabel = (id: string): string | undefined => { const entry = this.namespaceEntries.find((item) => item.root_node_id === id); return entry?.kind === 'personal' ? 'My files' : entry?.name; };

  mutationNotice = $state('');
  phase = $state<FilesPhase>('loading');
  node = $state.raw<NodeSummary | undefined>(undefined);
  children = $state.raw<NodeSummary[]>([]);
  uploadAvailability = $state<'hidden' | 'allowed' | 'denied' | 'sign-in'>('hidden');
  createDirectoryAllowed = $state(false);
  private updateSequence = 0;
  private readonly updatedNodes = new Map<string, { node: NodeSummary; sequence: number }>();
  private readonly confirmedDeletedIds = new Set<string>();
  private target = $state<string | null>(null);
  private sharedEntry = $state<string | null>(null);
  get inSharedWithMe(): boolean { return this.sharedEntry !== null; }
  get atSharedWithMe(): boolean { return this.inSharedWithMe && this.target === null; }
  childHref = (id: string): string => filesHref(id, this.atSharedWithMe ? id : this.sharedEntry);
  private rootId = $state<string | undefined>(undefined);
  private identityFingerprint: string | undefined;
  private generation = $state(0);
  get navigationVersion(): number { return this.generation; }

  isCurrentTarget = (target: string | null, sharedEntry: string | null = null): boolean => {
    if (this.generation === 0 || sharedEntry !== this.sharedEntry) return false;
    if (sharedEntry !== null) return target === this.target;
    return target === this.target || !!this.rootId && (target ?? this.rootId) === (this.target ?? this.rootId);
  };

  private clearContent = (): void => {
    this.node = undefined;
    this.children = [];
    this.uploadAvailability = 'hidden';
    this.createDirectoryAllowed = false;
    this.selectedNamespaceId = undefined;
    this.navigation.reset();
    this.preview?.reset();
  };
  private controller: AbortController | undefined;
  private disposed = false;

  readonly update: NodeUpdateState;
  readonly description: DescriptionState;
  readonly navigation: FilesNavigationState;
  readonly deletion: DeletionState;
  readonly rowDeletion: RowDeletionState;
  readonly rowEditing: RowEditingState;
  readonly dragMove: DragMoveState;
  readonly sharing: SharingEligibilityState;

  constructor(private readonly api: FilesApi, navigate?: (href: string) => Promise<void>, readonly preview?: FilePreviewState) {
    this.update = new NodeUpdateState(api.filesystem, this.acceptUpdate, this.reload, () => this.rootId);
    this.description = new DescriptionState(api.filesystem, this.acceptDescription, this.reload);
    this.rowEditing = new RowEditingState(api.filesystem, this.acceptUpdate, this.reload, () => this.rootId);
    this.sharing = new SharingEligibilityState(api.sharing);
    this.navigation = new FilesNavigationState(api.filesystem, () => this.rootId, this.namespaceLabel, () => this.sharedEntry, this.childHref);
    const deletionOperations = new SvelteMap<string, symbol>();
    const leaveDeletedFile = (parentId: string): Promise<void> => {
      if (this.inSharedWithMe) return navigate ? navigate(sharedWithMeHref) : this.load(null, '');
      return navigate ? navigate(filesHref(parentId)) : this.load(parentId);
    };
    this.deletion = new DeletionState(api, leaveDeletedFile, this.reload, this.acceptDeleted, true, deletionOperations);
    this.rowDeletion = new RowDeletionState(api, this.reload, this.acceptRowDeleted, deletionOperations);
    this.dragMove = new DragMoveState(
      () => this.children,
      (id) => this.rowEditing.controllers.get(id)?.update,
      (id) => this.rowEditing.controllers.get(id)?.description.pending === true || this.rowEditing.controllers.get(id)?.description.open === true || this.rowDeletion.controllers.get(id)?.pending === true || !!this.rowDeletion.controllers.get(id)?.confirmation || this.sharing.dialog.open
    );
  }

  observeAccountIdentity = (identity: import('#lib/header/accountIdentity.js').HeaderAccountIdentityState, force = false): void => {
    const fingerprint = JSON.stringify(identity.kind === 'visible' ? ['visible', identity.hiddenValues.id] : ['hidden']);
    if (this.disposed || !force && fingerprint === this.identityFingerprint) return;
    const previous = this.identityFingerprint;
    this.identityFingerprint = fingerprint;
    if (previous === undefined && !force) return;
    this.updatedNodes.clear();
    this.confirmedDeletedIds.clear();
    this.namespaceEntries = [];
    this.selectedNamespaceId = undefined;
    this.rootId = undefined;
    this.mutationNotice = '';
    this.clearContent();
    void this.reload();
  };

  private discoverNamespaces = async (signal: AbortSignal): Promise<{ error: unknown } | undefined> => {
    try {
      const listing = filesystemNamespacesSchema.parse({ namespaces: await this.api.filesystem.listNamespaces(signal) });
      if (signal.aborted) return;
      this.namespaceEntries = listing.namespaces;
      this.rootId = listing.namespaces.find((entry) => entry.kind === 'personal')?.root_node_id;
      if (!listing.namespaces.some((entry) => entry.id === this.selectedNamespaceId)) this.selectedNamespaceId = undefined;
      this.discoveryPhase = 'ready';
    } catch (error) {
      if (signal.aborted) return;
      this.namespaceEntries = [];
      this.rootId = undefined;
      this.selectedNamespaceId = undefined;
      this.discoveryPhase = readFailure(error);
      return { error };
    }
  };

  load = async (target: string | null, sharedEntry: string | null = null): Promise<void> => {
    if (this.disposed) return;
    this.preview?.reset();
    this.dragMove.reset();
    this.update.reset();
    this.description.reset();
    this.deletion.reset();
    this.rowDeletion.reset();
    this.rowEditing.reset();
    this.sharing.reset();
    const generation = ++this.generation;
    this.controller?.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    if (sharedEntry !== null || this.sharedEntry !== null) this.clearContent();
    else this.navigation.suspend();
    this.discoveryPhase = 'loading';
    this.target = target;
    this.sharedEntry = sharedEntry;
    this.phase = 'loading';
    const listingStartSequence = this.updateSequence;
    try {
      const selectedId = target === null ? null : nodeIdSchema.parse(target);
      const discovery = this.discoverNamespaces(signal);
      if (this.atSharedWithMe) {
        const { nodes } = childrenSchema.parse({ nodes: await this.api.filesystem.listSharedWithMe(signal) });
        if (signal.aborted) return;
        this.children = [...new Map(nodes.filter((node) => node.permissions.can_discover && !this.confirmedDeletedIds.has(node.id)).map((node) => [node.id, node])).values()];
        this.phase = 'ready';
        return;
      }
      const failure = await discovery;
      if (signal.aborted) return;
      if (failure) {
        this.clearContent();
        if (selectedId === null) throw failure.error;
      }
      const browseId = selectedId ?? this.rootId;
      if (!browseId) throw new Error('Home unavailable');
      const result = browseResultSchema.parse(await this.api.filesystem.browse(browseId, signal));
      if (this.disposed || generation !== this.generation || signal.aborted) return;
      if (result.node.id !== browseId) throw new Error('Unexpected browse target');
      const loadedNode = result.node;
      const known = this.updatedNodes.get(loadedNode.id)?.node;
      const node = known && known.revision > loadedNode.revision ? known : loadedNode;
      if (!node.permissions.can_discover) {
        this.clearContent();
        this.phase = 'missing';
        return;
      }
      const capabilities = new Map(result.capabilities.map((capability) => [capability.node_id, capability]));
      const current = capabilities.get(node.id)!;
      const namespaceRoot = [...result.breadcrumbs.items].reverse().map((item) => this.namespaceEntries.find((entry) => entry.root_node_id === item.id)).find((entry) => entry !== undefined);
      const visibility = node.visible_to;
      this.selectedNamespaceId = this.inSharedWithMe ? undefined : namespaceRoot?.id ?? (!result.breadcrumbs.complete && visibility.type === 'namespace' ? this.namespaceEntries.find((entry) => entry.id === visibility.namespace_id)?.id : undefined);
      this.uploadAvailability = 'hidden';
      this.createDirectoryAllowed = false;
      this.node = node;
      this.navigation.seed(node, result.breadcrumbs);
      if (typeof node.parent_id === 'string' && node.parent_id !== loadedNode.parent_id) void this.navigation.select(node);
      else this.navigation.acceptUpdatedNode(node);
      this.children = node.kind === 'directory' ? this.reconcileChildren(node.id, result.entries, listingStartSequence, true) : [];
      this.sharing.seed(result.capabilities.map((capability) => this.namespaceEntries.some((namespace) => namespace.root_node_id === capability.node_id) ? { ...capability, share: false } : capability));
      this.sharing.select(this.children);
      this.phase = 'ready';
      void this.preview?.select(node);
      void this.update.select(node, node.id === this.rootId ? { rename: false, move: false } : current);
      void this.description.select(node, current.edit_description);
      this.rowEditing.select(this.children, capabilities);
      if (node.kind === 'directory') {
        this.uploadAvailability = current.upload ? 'allowed' : 'denied';
        this.createDirectoryAllowed = current.create_directory;
        this.rowDeletion.select(this.children, capabilities);
      } else void this.deletion.select(node, current.delete);
    } catch (error) {
      if (this.disposed || generation !== this.generation || signal.aborted) return;
      this.clearContent();
      if (!this.atSharedWithMe && this.discoveryPhase === 'loading') this.discoveryPhase = readFailure(error);
      this.phase = readFailure(error);
    }
  };

  private reconcileChildren = (parentId: string, children: NodeSummary[], listingStartSequence: number, authoritative: boolean): NodeSummary[] => {
    const merged = new Map(children.map((child) => [child.id, child]));
    for (const [id, cached] of this.updatedNodes) {
      const listed = merged.get(id);
      if (listed) {
        if (listed.revision > cached.node.revision || authoritative && listed.revision === cached.node.revision && cached.sequence <= listingStartSequence) this.updatedNodes.set(id, { node: listed, sequence: cached.sequence });
        else merged.set(id, cached.node);
      } else if (cached.node.parent_id === parentId) {
        if (cached.sequence > listingStartSequence) merged.set(id, cached.node);
        else if (authoritative) this.updatedNodes.delete(id);
      }
    }
    const reconciled = Array.from(merged.values()).filter((child) => child.parent_id === parentId && child.permissions.can_discover && !this.confirmedDeletedIds.has(child.id));
    return reconciled.length === children.length && reconciled.every((child, index) => child === children[index]) ? children : reconciled;
  };

  private acceptUpdate = (node: NodeSummary): void => {
    if (this.disposed) return;
    const known = this.updatedNodes.get(node.id)?.node;
    if (known && known.revision > node.revision) return;
    const previousSequence = this.updateSequence;
    this.updatedNodes.set(node.id, { node, sequence: ++this.updateSequence });
    if (this.phase === 'loading' && !node.permissions.can_discover && this.children.some((child) => child.id === node.id)) {
      this.children = this.children.filter((child) => child.id !== node.id);
      this.sharing.remove(node.id);
    }
    if (this.phase === 'ready' && this.node?.kind === 'directory') {
      const previous = this.children;
      this.children = this.reconcileChildren(this.node.id, previous, previousSequence, false);
      for (const child of this.children) this.rowDeletion.controllers.get(child.id)?.acceptUpdatedNode(child);
      for (const child of previous) {
        if (!this.children.some((current) => current.id === child.id)) this.sharing.remove(child.id);
      }
      this.sharing.select(this.children);
      this.rowDeletion.select(this.children);
      this.rowEditing.select(this.children);
    }
    if (this.node?.id !== node.id || this.node.revision > node.revision) return;
    if (this.phase !== 'ready') {
      if (node.permissions.can_discover) return;
      if ((this.target ?? this.rootId) !== node.id) {
        this.clearContent();
        return;
      }
    }
    const previousParent = typeof this.node.parent_id === 'string' ? this.node.parent_id : undefined;
    const nextParent = typeof node.parent_id === 'string' ? node.parent_id : undefined;
    const parentChanged = previousParent !== nextParent;
    if (!node.permissions.can_discover) {
      ++this.generation;
      this.controller?.abort();
      this.dragMove.reset();
      this.update.reset();
      this.description.reset();
      this.deletion.reset();
      this.rowEditing.reset();
      this.rowDeletion.reset();
      this.sharing.reset();
      this.navigation.reset();
      this.preview?.reset();
      this.node = undefined;
      this.children = [];
      this.uploadAvailability = 'hidden';
      this.createDirectoryAllowed = false;
      this.selectedNamespaceId = undefined;
      this.phase = 'missing';
      return;
    }
    if (parentChanged) {
      void this.reload();
      return;
    }
    this.node = node;
    void this.preview?.select(node);
    this.description.acceptUpdatedNode(node);
    this.update.acceptUpdatedNode(node);
    if (node.kind === 'file') this.deletion.acceptUpdatedNode(node);
    this.navigation.acceptUpdatedNode(node);
  };

  private acceptDescription = (node: NodeSummary): void => { this.acceptUpdate(node); };

  private acceptDeleted = (node: NodeSummary): void => {
    if (this.disposed) return;
    this.confirmedDeletedIds.add(node.id);
    this.sharing.remove(node.id);
    if (this.node?.id === node.id) this.preview?.reset();
    this.children = this.children.filter((child) => child.id !== node.id);
    this.mutationNotice = `“${node.name}” was deleted from the workspace.`;
  };

  private acceptRowDeleted = (node: NodeSummary): void => {
    if (this.disposed) return;
    this.confirmedDeletedIds.add(node.id);
    const selectedId = this.target === null ? this.rootId : this.target;
    if (selectedId === node.parent_id || this.atSharedWithMe && this.children.some((child) => child.id === node.id)) this.acceptDeleted(node);
  };

  nodeForDetails = (node: NodeSummary): NodeSummary => {
    const visibility = node.visible_to;
    if (!this.inSharedWithMe || visibility.type === 'restricted' || this.namespaceEntries.some((entry) => entry.id === visibility.namespace_id)) return node;
    return { ...node, visible_to: { type: 'restricted' } };
  };

  nodePresentation = (node: NodeSummary): Readonly<{ name: string; isHome: boolean; iconKind: 'home' | 'file' | 'directory' }> => {
    const isHome = node.kind === 'directory' && node.id === this.rootId;
    const name = this.atSharedWithMe ? node.name : this.namespaceLabel(node.id) ?? node.name;
    return { name, isHome, iconKind: isHome ? 'home' : node.kind };
  };

  get contentLoading(): boolean {
    return this.phase === 'loading' || this.node?.kind === 'file' && this.preview?.phase === 'loading';
  }

  get atNamespaceRoot(): boolean {
    return !!this.node && this.namespaceEntries.some((namespace) => namespace.root_node_id === this.node?.id);
  }

  get atPersonalRoot(): boolean {
    return !!this.node && this.node.id === this.rootId;
  }

  get locationName(): string {
    return this.node ? this.navigation.label(this.node) || 'Files' : 'Files';
  }

  reload = async (): Promise<void> => this.load(this.target, this.sharedEntry);

  rejectUploadAccess = (parentId: string, phase: 'denied' | 'sign-in'): void => {
    if (this.disposed || this.node?.id !== parentId) return;
    this.uploadAvailability = phase;
  };

  acceptCreated = async (parentId: string, generation: number, node: NodeSummary): Promise<void> => {
    if (this.disposed || node.parent_id !== parentId) return;
    if (generation === this.generation && this.phase === 'ready' && this.node?.id === parentId) {
      this.children = [...this.children.filter((child) => child.id !== node.id), node];
      this.rowDeletion.select([node]);
      this.rowEditing.select([node]);
      this.sharing.select([node]);
      return;
    }
    const selectedId = this.target === null ? this.rootId : this.target;
    if (selectedId !== parentId || (this.phase !== 'ready' && this.phase !== 'loading')) return;
    await this.reload();
  };

  creationTarget = (): { parentId: string; generation: number } | undefined => {
    if (this.phase !== 'ready' || this.node?.kind !== 'directory') return undefined;
    return { parentId: this.node.id, generation: this.generation };
  };

  dispose = (): void => {
    this.disposed = true;
    this.clearContent();
    this.updatedNodes.clear();
    this.confirmedDeletedIds.clear();
    this.target = null;
    this.sharedEntry = null;
    this.mutationNotice = '';
    this.namespaceEntries = [];
    this.selectedNamespaceId = undefined;
    this.rootId = undefined;
    this.preview?.dispose();
    this.dragMove.dispose();
    this.update.dispose();
    this.description.dispose();
    this.navigation.dispose();
    this.deletion.dispose();
    this.rowDeletion.dispose();
    this.rowEditing.dispose();
    this.sharing.dispose();
    ++this.generation;
    this.controller?.abort();
  };
}
