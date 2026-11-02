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
import { nodeIdSchema, type NodeSummary } from '../domain/schemas';
import { readFailure, type FilesPhase } from '../errors';

export function filesHref(id?: string): string {
  return id ? '/files?node=' + encodeURIComponent(id) : '/files';
}

export class FilesState {
  mutationNotice = $state('');
  phase = $state<FilesPhase>('loading');
  node = $state.raw<NodeSummary | undefined>(undefined);
  children = $state.raw<NodeSummary[]>([]);
  uploadAvailability = $state<'hidden' | 'loading' | 'allowed' | 'denied' | 'sign-in' | 'error'>('hidden');
  private eligibilityGeneration = 0;
  private updateSequence = 0;
  private readonly updatedNodes = new Map<string, { node: NodeSummary; sequence: number }>();
  private readonly confirmedDeletedIds = new Set<string>();
  private target: string | null = null;
  private rootId: string | undefined;
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
    this.update = new NodeUpdateState(api.filesystem, this.acceptUpdate, this.reload);
    this.description = new DescriptionState(api.filesystem, this.acceptDescription, this.reload);
    this.rowEditing = new RowEditingState(api.filesystem, this.acceptUpdate, this.reload);
    this.sharing = new SharingEligibilityState(api.sharing);
    this.navigation = new FilesNavigationState(api.filesystem);
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
    try {
      const loadedNode = target === null
        ? await this.api.filesystem.getRoot(signal)
        : await this.api.filesystem.getNode(nodeIdSchema.parse(target), signal);
      if (this.disposed || generation !== this.generation) return;
      const known = this.updatedNodes.get(loadedNode.id)?.node;
      let node = known && known.revision > loadedNode.revision ? known : loadedNode;
      if (target === null) this.rootId = node.id;
      this.node = node;
      this.sharing.selectCurrent(node);
      void this.navigation.select(node);
      const listingStartSequence = this.updateSequence;
      const children = node.kind === 'directory' ? await this.api.filesystem.listChildren(node.id, signal) : [];
      if (this.disposed || generation !== this.generation) return;
      const latest = this.updatedNodes.get(node.id)?.node;
      if (latest && latest.revision > node.revision) {
        node = latest;
        this.node = latest;
        void this.navigation.select(latest);
      }
      this.children = node.kind === 'directory' ? this.reconcileChildren(node.id, children, listingStartSequence, true) : [];
      this.phase = 'ready';
      void this.update.select(node);
      void this.description.select(node);
      this.sharing.select(this.children);
      this.rowEditing.select(this.children);
      if (node.kind === 'directory') {
        void this.checkUploadAvailability();
        void this.rowDeletion.select(this.children);
      }
      else void this.deletion.select(node);
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
        if (listed.revision > cached.node.revision) this.updatedNodes.set(id, { node: listed, sequence: cached.sequence });
        else merged.set(id, cached.node);
      } else if (cached.node.parent_id === parentId) {
        if (cached.sequence > listingStartSequence) merged.set(id, cached.node);
        else if (authoritative) this.updatedNodes.delete(id);
      }
    }
    const reconciled = Array.from(merged.values()).filter((child) => child.parent_id === parentId && !this.confirmedDeletedIds.has(child.id));
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
    this.node = node;
    this.description.acceptUpdatedNode(node);
    this.update.acceptUpdatedNode(node);
    if (node.kind === 'file') this.deletion.acceptUpdatedNode(node);
    void this.navigation.select(node);
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

  reload = async (): Promise<void> => this.load(this.target);

  rejectUploadAccess = (parentId: string, phase: 'denied' | 'sign-in'): void => {
    if (this.disposed || this.node?.id !== parentId) return;
    ++this.eligibilityGeneration;
    this.uploadAvailability = phase;
  };

  checkUploadAvailability = async (): Promise<void> => {
    const target = this.creationTarget();
    if (!target || this.disposed) return;
    const eligibilityGeneration = ++this.eligibilityGeneration;
    this.uploadAvailability = 'loading';
    try {
      await this.api.filesystem.checkUploadEligibility(target.parentId, this.controller?.signal);
      if (this.disposed || target.generation !== this.generation || eligibilityGeneration !== this.eligibilityGeneration) return;
      this.uploadAvailability = 'allowed';
    } catch (error) {
      if (this.disposed || target.generation !== this.generation || eligibilityGeneration !== this.eligibilityGeneration) return;
      const failure = readFailure(error);
      this.uploadAvailability = failure === 'sign-in' ? 'sign-in' : failure === 'denied' || failure === 'missing' ? 'denied' : 'error';
    }
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
