import { SvelteMap } from 'svelte/reactivity';
import { FilesNavigationState } from './navigation-state.svelte';
import { RowDeletionState } from './row-deletion-state.svelte';
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
  private readonly confirmedDeletedIds = new Set<string>();
  private target: string | null = null;
  private rootId: string | undefined;
  private generation = 0;
  private controller: AbortController | undefined;
  private disposed = false;

  readonly navigation: FilesNavigationState;
  readonly deletion: DeletionState;
  readonly rowDeletion: RowDeletionState;

  constructor(private readonly api: FilesApi, openParent?: (id: string) => Promise<void>) {
    this.navigation = new FilesNavigationState(api.filesystem);
    const deletionOperations = new SvelteMap<string, symbol>();
    this.deletion = new DeletionState(api, openParent ?? ((id) => this.load(id)), this.reload, this.acceptDeleted, true, deletionOperations);
    this.rowDeletion = new RowDeletionState(api, this.reload, this.acceptRowDeleted, deletionOperations);
  }

  load = async (target: string | null): Promise<void> => {
    if (this.disposed) return;
    this.deletion.reset();
    this.rowDeletion.reset();
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
      const node = target === null
        ? await this.api.filesystem.getRoot(signal)
        : await this.api.filesystem.getNode(nodeIdSchema.parse(target), signal);
      if (this.disposed || generation !== this.generation) return;
      if (target === null) this.rootId = node.id;
      this.node = node;
      void this.navigation.select(node);
      const children = node.kind === 'directory' ? await this.api.filesystem.listChildren(node.id, signal) : [];
      if (this.disposed || generation !== this.generation) return;
      this.children = children.filter((child) => !this.confirmedDeletedIds.has(child.id));
      this.phase = 'ready';
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

  private acceptDeleted = (node: NodeSummary): void => {
    if (this.disposed) return;
    this.confirmedDeletedIds.add(node.id);
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
    this.navigation.dispose();
    this.deletion.dispose();
    this.rowDeletion.dispose();
    ++this.generation;
    this.controller?.abort();
  };
}
