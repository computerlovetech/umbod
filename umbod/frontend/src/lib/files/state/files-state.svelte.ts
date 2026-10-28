import type { FilesApi } from '../api';
import { nodeIdSchema, type NodeSummary, type UploadPolicy } from '../domain/schemas';
import { readFailure, type FilesPhase } from '../errors';

export interface VisitedFolder {
  id: string;
  name: string;
}

export function filesHref(id?: string): string {
  return id ? '/files?node=' + encodeURIComponent(id) : '/files';
}

export class FilesState {
  phase = $state<FilesPhase>('loading');
  node = $state.raw<NodeSummary | undefined>(undefined);
  children = $state.raw<NodeSummary[]>([]);
  trail = $state.raw<VisitedFolder[]>([]);
  uploadPolicy = $state.raw<UploadPolicy | undefined>(undefined);
  uploadAvailability = $state<'hidden' | 'loading' | 'allowed' | 'denied' | 'sign-in' | 'error'>('hidden');
  private policyGeneration = 0;
  private readonly visited = new Map<string, VisitedFolder[]>();
  private target: string | null = null;
  private rootId: string | undefined;
  private generation = 0;
  private controller: AbortController | undefined;
  private disposed = false;

  constructor(private readonly api: FilesApi) {}

  load = async (target: string | null): Promise<void> => {
    if (this.disposed) return;
    const generation = ++this.generation;
    this.controller?.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const previous = this.node;
    const previousTrail = this.trail;
    this.target = target;
    this.node = undefined;
    this.children = [];
    this.trail = [];
    this.phase = 'loading';
    this.uploadPolicy = undefined;
    this.uploadAvailability = 'hidden';
    try {
      const node = target === null
        ? await this.api.filesystem.getRoot(signal)
        : await this.api.filesystem.getNode(nodeIdSchema.parse(target), signal);
      if (this.disposed || generation !== this.generation) return;
      if (target === null) this.rootId = node.id;
      const children = node.kind === 'directory' ? await this.api.filesystem.listChildren(node.id, signal) : [];
      if (this.disposed || generation !== this.generation) return;
      this.trail = this.resolveTrail(node, previous, previousTrail);
      this.visited.set(node.id, this.trail);
      this.node = node;
      this.children = children;
      this.phase = 'ready';
      if (node.kind === 'directory') void this.checkUploadAvailability();
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.phase = readFailure(error);
    }
  };

  reload = async (): Promise<void> => this.load(this.target);

  rejectUploadAccess = (parentId: string, phase: 'denied' | 'sign-in'): void => {
    if (this.disposed || this.node?.id !== parentId) return;
    ++this.policyGeneration;
    this.uploadPolicy = undefined;
    this.uploadAvailability = phase;
  };

  checkUploadAvailability = async (): Promise<void> => {
    const target = this.creationTarget();
    if (!target || this.disposed) return;
    const policyGeneration = ++this.policyGeneration;
    this.uploadAvailability = 'loading';
    this.uploadPolicy = undefined;
    try {
      const policy = await this.api.filesystem.getUploadPolicy(target.parentId, this.controller?.signal);
      if (this.disposed || target.generation !== this.generation || policyGeneration !== this.policyGeneration) return;
      this.uploadPolicy = policy;
      this.uploadAvailability = 'allowed';
    } catch (error) {
      if (this.disposed || target.generation !== this.generation || policyGeneration !== this.policyGeneration) return;
      const failure = readFailure(error);
      this.uploadAvailability = failure === 'sign-in' ? 'sign-in' : failure === 'denied' || failure === 'missing' ? 'denied' : 'error';
    }
  };

  acceptCreated = async (parentId: string, generation: number, node: NodeSummary): Promise<void> => {
    if (this.disposed || node.parent_id !== parentId) return;
    if (generation === this.generation && this.phase === 'ready' && this.node?.id === parentId) {
      this.children = [...this.children.filter((child) => child.id !== node.id), node];
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
    ++this.generation;
    this.controller?.abort();
  };

  private resolveTrail(node: NodeSummary, previous: NodeSummary | undefined, trail: VisitedFolder[]): VisitedFolder[] {
    if (typeof node.parent_id !== 'string') return [];
    const known = this.visited.get(node.id);
    const ancestors = known
      ? known.filter((folder) => folder.id !== node.id)
      : previous?.kind === 'directory' && node.parent_id === previous.id ? trail : [];
    return node.kind === 'directory' ? [...ancestors, { id: node.id, name: node.name }] : ancestors;
  }
}
