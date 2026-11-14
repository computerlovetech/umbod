import type { FilesystemApi } from '../api';
import { breadcrumbsSchema, type BreadcrumbItem, type Breadcrumbs } from '../domain/schemas';
import { readFailure, type FilesPhase } from '../errors';

export class FilesNavigationState {
  phase = $state<FilesPhase>('loading');
  path = $state.raw<Breadcrumbs | undefined>(undefined);
  menuOpen = $state(false);
  private selected: BreadcrumbItem | undefined;
  private generation = 0;
  private controller: AbortController | undefined;
  private disposed = false;

  constructor(private readonly api: FilesystemApi, private readonly personalRoot: () => string | undefined = () => undefined, private readonly namespaceLabel: (id: string) => string | undefined = () => undefined) {}

  readonly displayItems: readonly BreadcrumbItem[] = $derived.by(() => {
    const items = this.path?.items ?? [];
    const index = items.findLastIndex((item) => this.isPersonalRoot(item) || this.namespaceLabel(item.id) !== undefined);
    return index < 0 ? items : items.slice(index);
  });

  get rootIcon(): 'home' | 'namespace' | 'folder' {
    const root = this.displayItems[0];
    if (!root) return 'folder';
    if (this.isPersonalRoot(root)) return 'home';
    return this.namespaceLabel(root.id) !== undefined ? 'namespace' : 'folder';
  }

  get displayComplete(): boolean {
    const root = this.displayItems[0];
    return !!root && (this.isPersonalRoot(root) || this.namespaceLabel(root.id) !== undefined || this.path?.complete === true);
  }

  private isPersonalRoot(item: BreadcrumbItem): boolean {
    return item.id === this.personalRoot();
  }

  suspend = (): void => {
    ++this.generation;
    this.controller?.abort();
    this.closeMenu();
    this.phase = 'loading';
  };

  reset = (): void => {
    this.suspend();
    this.selected = undefined;
    this.path = undefined;
    this.phase = 'loading';
  };

  select = async (node: BreadcrumbItem): Promise<void> => {
    if (this.disposed) return;
    this.reset();
    this.selected = node;
    await this.reload();
  };

  seed = (node: BreadcrumbItem, path: Breadcrumbs): void => {
    if (this.disposed) return;
    this.reset();
    this.selected = node;
    this.path = path;
    this.phase = 'ready';
  };

  acceptUpdatedNode = (node: BreadcrumbItem): void => {
    if (this.disposed || this.selected?.id !== node.id || !this.path) return;
    this.selected = node;
    this.path = { ...this.path, items: this.path.items.map((item) => item.id === node.id ? { ...item, name: node.name } : item) };
  };

  reload = async (): Promise<void> => {
    const selected = this.selected;
    if (this.disposed || !selected) return;
    const generation = ++this.generation;
    this.controller?.abort();
    this.controller = new AbortController();
    this.closeMenu();
    this.path = undefined;
    this.phase = 'loading';
    try {
      const path = breadcrumbsSchema.parse(await this.api.getBreadcrumbs(selected.id, this.controller.signal));
      if (this.disposed || generation !== this.generation) return;
      const target = path.items.at(-1);
      const root = path.items[0];
      if (path.complete && (root.kind !== 'directory')) throw new Error('Invalid root');
      if (target?.id !== selected.id || target.kind !== selected.kind || new Set(path.items.map((item) => item.id)).size !== path.items.length || path.items.slice(0, -1).some((item) => item.kind !== 'directory')) throw new Error('Invalid path');
      this.path = { ...path, items: path.items.map((item) => item.id === selected.id ? { ...item, name: selected.name } : item) };
      this.phase = 'ready';
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.phase = readFailure(error);
    }
  };

  get parent(): BreadcrumbItem | undefined {
    const parent = this.displayItems.at(-2);
    return parent?.kind === 'directory' ? parent : undefined;
  }

  get atRoot(): boolean {
    const items = this.displayItems;
    return items.length === 1 && items[0].kind === 'directory' && this.displayComplete;
  }

  label = (item: BreadcrumbItem): string => this.namespaceLabel(item.id) ?? (this.isPersonalRoot(item) ? 'My files' : item.name || 'Files');

  href = (item: BreadcrumbItem): string => this.isPersonalRoot(item) ? '/files' : '/files?node=' + encodeURIComponent(item.id);

  readonly visibleItems: readonly BreadcrumbItem[] = $derived.by(() => {
    const items = this.displayItems;
    return items.length > 4 ? [items[0], ...items.slice(-2)] : items;
  });

  readonly omittedAncestors: readonly BreadcrumbItem[] = $derived.by(() => {
    const items = this.displayItems;
    return items.length > 4 ? items.slice(1, -2) : [];
  });

  closeMenu = (): void => {
    this.menuOpen = false;
  };

  setMenuOpen = (open: boolean): void => {
    this.menuOpen = !this.disposed && this.omittedAncestors.length > 0 && open;
  };

  dispose = (): void => {
    this.disposed = true;
    this.reset();
  };
}
