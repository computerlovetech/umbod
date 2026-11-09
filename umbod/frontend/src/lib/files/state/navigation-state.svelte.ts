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

  constructor(private readonly api: FilesystemApi, private readonly personalRoot: () => string | undefined = () => undefined) {}

  get displayItems(): BreadcrumbItem[] {
    return this.path?.items ?? [];
  }

  get displayComplete(): boolean {
    return this.path?.complete === true;
  }

  private isPersonalRoot(item: BreadcrumbItem): boolean {
    return item.id === this.personalRoot();
  }

  private isCanonicalRoot(item: BreadcrumbItem): boolean {
    return this.path?.complete === true && this.path.items[0].id === item.id;
  }

  reset = (): void => {
    ++this.generation;
    this.controller?.abort();
    this.closeMenu();
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
      if (path.complete && (root.kind !== 'directory' || root.name !== '')) throw new Error('Invalid root');
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
    return items.length === 1 && items[0].kind === 'directory' && this.isCanonicalRoot(items[0]);
  }

  label = (item: BreadcrumbItem): string => this.isPersonalRoot(item) ? 'Home' : this.isCanonicalRoot(item) ? 'Root' : item.name;

  href = (item: BreadcrumbItem): string => this.isPersonalRoot(item) ? '/files' : '/files?node=' + encodeURIComponent(item.id);

  get visibleItems(): BreadcrumbItem[] {
    const items = this.displayItems;
    return items.length > 4 ? [items[0], ...items.slice(-2)] : items;
  }

  get omittedAncestors(): BreadcrumbItem[] {
    const items = this.displayItems;
    return items.length > 4 ? items.slice(1, -2) : [];
  }

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
