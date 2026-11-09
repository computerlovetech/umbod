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
import { browseResultSchema, nodeIdSchema, nodeSummarySchema, type NodeSummary } from '../domain/schemas';
import { readFailure, type FilesPhase } from '../errors';

export function filesHref(id?: string): string {
  return id ? '/files?node=' + encodeURIComponent(id) : '/files';
}

export class FilesState {
  mutationNotice = $state('');
  phase = $state<FilesPhase>('loading');
  node = $state.raw<NodeSummary | undefined>(undefined);
  children = $state.raw<NodeSummary[]>([]);
  uploadAvailability = $state<'hidden' | 'allowed' | 'denied' | 'sign-in'>('hidden');
  createDirectoryAllowed = $state(false);
  private updateSequence = 0;
  private readonly updatedNodes = new Map<string, { node: NodeSummary; sequence: number }>();
  private readonly confirmedDeletedIds = new Set<string>();
  private target: string | null = null;
  private rootId = $state<string | undefined>(undefined);
  private generation = 0;
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

  constructor(private readonly api: FilesApi, openParent?: (id: string) => Promise<void>) {
    this.update = new NodeUpdateState(api.filesystem, this.acceptUpdate, this.reload, () => this.rootId);
    this.description = new DescriptionState(api.filesystem, this.acceptDescription, this.reload);
    this.rowEditing = new RowEditingState(api.filesystem, this.acceptUpdate, this.reload, () => this.rootId);
    this.sharing = new SharingEligibilityState(api.sharing, (node) => node.id === this.rootId ? 'Files' : node.name || 'Files');
    this.navigation = new FilesNavigationState(api.filesystem, () => this.rootId);
    const deletionOperations = new SvelteMap<string, symbol>();
    this.deletion = new DeletionState(api, openParent ?? ((id) => this.load(id)), this.reload, this.acceptDeleted, true, deletionOperations);
    this.rowDeletion = new RowDeletionState(api, this.reload, this.acceptRowDeleted, deletionOperations);
    this.dragMove = new DragMoveState(
      () => this.children,
      (id) => this.rowEditing.controllers.get(id)?.update,
      (id) => this.rowEditing.controllers.get(id)?.description.pending === true || this.rowEditing.controllers.get(id)?.description.open === true || this.rowDeletion.controllers.get(id)?.pending === true || !!this.rowDeletion.controllers.get(id)?.confirmation || this.sharing.dialog.open
    );
  }

  load = async (target: string | null): Promise<void> => {
    if (this.disposed) return;
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
    this.navigation.reset();
    this.target = target;
    this.node = undefined;
    this.children = [];
    this.phase = 'loading';
    this.uploadAvailability = 'hidden';
    this.createDirectoryAllowed = false;
    const listingStartSequence = this.updateSequence;
    try {
      const selectedId = target === null ? null : nodeIdSchema.parse(target);
      if (!this.rootId) {
        try {
          const home = nodeSummarySchema.parse(await this.api.filesystem.getHome(signal));
          if (this.disposed || generation !== this.generation || signal.aborted) return;
          if (home.kind !== 'directory') throw new Error('Invalid home');
          this.rootId = home.id;
        } catch (error) {
          if (selectedId === null || signal.aborted) throw error;
        }
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
        this.phase = 'missing';
        return;
      }
      const capabilities = new Map(result.capabilities.map((capability) => [capability.node_id, capability]));
      const current = capabilities.get(node.id)!;
      this.node = node;
      this.navigation.seed(node, result.breadcrumbs);
      if (typeof node.parent_id === 'string' && node.parent_id !== loadedNode.parent_id) void this.navigation.select(node);
      else this.navigation.acceptUpdatedNode(node);
      this.children = node.kind === 'directory' ? this.reconcileChildren(node.id, result.entries, listingStartSequence, true) : [];
      this.sharing.seed(result.capabilities);
      this.phase = 'ready';
      void this.update.select(node, node.id === this.rootId ? { rename: false, move: false } : current);
      void this.description.select(node, current.edit_description);
      this.sharing.select(this.children);
      this.rowEditing.select(this.children, capabilities);
      if (node.kind === 'directory') {
        this.uploadAvailability = current.upload ? 'allowed' : 'denied';
        this.createDirectoryAllowed = current.create_directory;
        this.rowDeletion.select(this.children, capabilities);
      } else void this.deletion.select(node, current.delete);
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
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
    if (this.phase === 'ready' && this.node?.kind === 'directory') {
      const previous = this.children;
      this.children = this.reconcileChildren(this.node.id, previous, previousSequence, false);
      for (const child of previous) {
        if (!this.children.some((current) => current.id === child.id)) this.sharing.remove(child.id);
      }
      for (const child of this.children) this.rowDeletion.controllers.get(child.id)?.acceptUpdatedNode(child);
      this.sharing.select(this.children);
      this.rowDeletion.select(this.children);
      this.rowEditing.select(this.children);
    }
    if (this.node?.id !== node.id || this.node.revision > node.revision) return;
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
      this.node = undefined;
      this.children = [];
      this.uploadAvailability = 'hidden';
      this.createDirectoryAllowed = false;
      this.phase = 'missing';
      return;
    }
    if (parentChanged) {
      void this.load(this.target);
      return;
    }
    this.node = node;
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
    this.children = this.children.filter((child) => child.id !== node.id);
    this.mutationNotice = `“${node.name}” was deleted from the workspace.`;
  };

  private acceptRowDeleted = (node: NodeSummary): void => {
    if (this.disposed) return;
    this.confirmedDeletedIds.add(node.id);
    const selectedId = this.target === null ? this.rootId : this.target;
    if (selectedId === node.parent_id) this.acceptDeleted(node);
  };

  nodePresentation = (node: NodeSummary): Readonly<{ name: string; isHome: boolean; iconKind: 'home' | 'file' | 'directory' }> => {
    const isHome = node.kind === 'directory' && node.id === this.rootId;
    return { name: isHome ? 'Home' : node.name, isHome, iconKind: isHome ? 'home' : node.kind };
  };

  get atPersonalRoot(): boolean {
    return !!this.node && this.node.id === this.rootId;
  }

  get locationName(): string {
    return this.atPersonalRoot ? 'Files' : this.node ? this.navigation.label(this.node) || 'Files' : 'Files';
  }

  reload = async (): Promise<void> => this.load(this.target);

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
