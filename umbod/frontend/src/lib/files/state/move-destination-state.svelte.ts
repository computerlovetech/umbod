import { SvelteMap } from 'svelte/reactivity';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { FilesystemApi } from '../api';
import { breadcrumbsSchema, type BreadcrumbItem, type NodeSummary } from '../domain/schemas';
import { FilesNavigationState } from './navigation-state.svelte';

type BranchPhase = 'idle' | 'loading' | 'ready' | 'error';

type Branch = Readonly<{
  node: BreadcrumbItem;
  children: readonly NodeSummary[];
  phase: BranchPhase;
  expanded: boolean;
  writable: boolean;
}>;

export type DestinationFolder = Readonly<{
  id: string;
  name: string;
  current: boolean;
  selected: boolean;
  selectable: boolean;
  expanded: boolean;
  expandable: boolean;
  phase: BranchPhase;
  children: readonly DestinationFolder[];
}>;

export class MoveDestinationState {
  private readonly navigation: FilesNavigationState;
  private readonly branches = new SvelteMap<string, Branch>();
  private source: NodeSummary | undefined;
  private rootId = $state<string | undefined>(undefined);
  private destination = $state.raw<NodeSummary | undefined>(undefined);
  private targetId = $state<string | undefined>(undefined);
  private initializing = $state(false);
  private checking = $state(false);
  private allowed = $state(false);
  private message = $state('');
  private generation = 0;
  private selectionGeneration = 0;

  constructor(private readonly api: FilesystemApi, private readonly personalRoot: () => string | undefined, private readonly locked: () => boolean) {
    this.navigation = new FilesNavigationState(api, personalRoot);
  }

  get folders(): readonly DestinationFolder[] {
    return this.rootId ? this.project(this.rootId, new Set()) : [];
  }
  get selected(): NodeSummary | undefined { return this.destination; }
  get selectedName(): string { return this.destination ? this.navigation.label(this.destination) : ''; }
  get loading(): boolean { return this.initializing; }
  get selecting(): boolean { return this.checking; }
  get error(): string { return this.message; }
  get canSubmit(): boolean { return this.allowed && !this.checking && !this.initializing; }
  get canRetry(): boolean { return !this.rootId && !this.initializing && !!this.message; }

  reset = (): void => {
    ++this.generation;
    ++this.selectionGeneration;
    this.navigation.reset();
    this.branches.clear();
    this.source = undefined;
    this.rootId = undefined;
    this.destination = undefined;
    this.targetId = undefined;
    this.initializing = false;
    this.checking = false;
    this.allowed = false;
    this.message = '';
  };

  open = async (source: NodeSummary): Promise<void> => {
    this.reset();
    this.source = source;
    if (typeof source.parent_id !== 'string') return;
    const generation = this.generation;
    this.initializing = true;
    try {
      const parent = await this.api.getNode(source.parent_id);
      if (generation !== this.generation) return;
      await this.navigation.select(parent);
      if (generation !== this.generation) return;
      if (this.navigation.phase !== 'ready') throw new Error('Destination path unavailable');
      const items = this.navigation.displayItems;
      const homeIndex = items.findIndex((item) => item.id === this.personalRoot());
      const path = homeIndex < 0 ? items : items.slice(homeIndex);
      for (const node of path) {
        this.branches.set(node.id, { node, children: [], phase: 'idle', expanded: true, writable: node.id === parent.id ? parent.permissions.can_write : true });
      }
      this.rootId = path[0]?.id;
      await Promise.all(path.map((node) => this.loadChildren(node.id)));
    } catch {
      if (generation === this.generation) this.message = 'Could not load folders.';
    } finally {
      if (generation === this.generation) this.initializing = false;
    }
  };

  retry = async (): Promise<void> => {
    if (this.source && this.canRetry && !this.locked()) await this.open(this.source);
  };

  toggle = async (id: string): Promise<void> => {
    const branch = this.branches.get(id);
    if (!branch || this.locked()) return;
    this.branches.set(id, { ...branch, expanded: !branch.expanded });
    if (branch.expanded) {
      if (this.targetId && this.contains(id, this.targetId)) this.clearSelection();
    } else if (branch.phase === 'idle' || branch.phase === 'error') await this.loadChildren(id);
  };

  retryBranch = async (id: string): Promise<void> => {
    if (!this.locked() && this.branches.get(id)?.phase === 'error') await this.loadChildren(id);
  };

  select = async (id: string): Promise<void> => {
    const branch = this.branches.get(id);
    const source = this.source;
    if (!branch || !source || this.locked() || id === source.parent_id || id === source.id || !branch.writable) return;
    const generation = this.generation;
    const selection = ++this.selectionGeneration;
    this.destination = undefined;
    this.targetId = id;
    this.allowed = false;
    this.checking = true;
    this.message = '';
    try {
      const folder = await this.api.getNode(id);
      if (generation !== this.generation || selection !== this.selectionGeneration) return;
      if (folder.kind !== 'directory') throw new Error('Not a folder');
      this.destination = folder;
      const path = breadcrumbsSchema.parse(await this.api.getBreadcrumbs(id));
      if (generation !== this.generation || selection !== this.selectionGeneration) return;
      if (path.items.at(-1)?.id !== id || path.items.some((item) => item.kind !== 'directory') || new Set(path.items.map((item) => item.id)).size !== path.items.length) throw new Error('Invalid destination path');
      if (path.items.some((item) => item.id === source.id)) {
        this.clearSelection();
        return;
      }
      await this.api.checkUpdateEligibility(id);
      if (generation === this.generation && selection === this.selectionGeneration) this.allowed = true;
    } catch (error) {
      if (generation !== this.generation || selection !== this.selectionGeneration) return;
      this.allowed = false;
      if (error instanceof HttpError && [403, 404].includes(error.status)) {
        this.destination = undefined;
        this.targetId = undefined;
        const current = this.branches.get(id);
        if (current) this.branches.set(id, { ...current, writable: false });
      } else this.message = 'Could not check destination. Try again.';
    } finally {
      if (generation === this.generation && selection === this.selectionGeneration) this.checking = false;
    }
  };

  private clearSelection(): void {
    ++this.selectionGeneration;
    this.destination = undefined;
    this.targetId = undefined;
    this.allowed = false;
    this.checking = false;
    this.message = '';
  }

  private contains(parentId: string, id: string): boolean {
    const children = this.branches.get(parentId)?.children ?? [];
    return children.some((child) => child.id === id || this.contains(child.id, id));
  }

  private async loadChildren(id: string): Promise<void> {
    const branch = this.branches.get(id);
    if (!branch || branch.phase === 'loading') return;
    const generation = this.generation;
    this.branches.set(id, { ...branch, phase: 'loading' });
    try {
      const children = await this.api.listChildren(id);
      if (generation !== this.generation) return;
      const folders = children.filter((node) => node.kind === 'directory' && node.id !== this.source?.id && node.parent_id === id);
      for (const node of folders) {
        const existing = this.branches.get(node.id);
        this.branches.set(node.id, { node, children: existing?.children ?? [], phase: existing?.phase ?? 'idle', expanded: existing?.expanded ?? false, writable: node.permissions.can_write });
      }
      const current = this.branches.get(id)!;
      this.branches.set(id, { ...current, children: folders, phase: 'ready' });
    } catch {
      if (generation === this.generation) this.branches.set(id, { ...this.branches.get(id)!, phase: 'error' });
    }
  }

  private project(id: string, ancestors: ReadonlySet<string>): DestinationFolder[] {
    const branch = this.branches.get(id);
    if (!branch || ancestors.has(id)) return [];
    const path = new Set([...ancestors, id]);
    return [{
      id, name: this.navigation.label(branch.node), current: id === this.source?.parent_id,
      selected: id === this.targetId, selectable: id !== this.source?.parent_id && branch.writable,
      expanded: branch.expanded, expandable: branch.phase !== 'ready' || branch.children.length > 0,
      phase: branch.phase,
      children: branch.expanded ? branch.children.flatMap((child) => this.project(child.id, path)) : []
    }];
  }
}
