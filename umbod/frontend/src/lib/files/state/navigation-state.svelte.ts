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

  constructor(private readonly api: FilesystemApi) {}

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
      this.path = path;
      this.phase = 'ready';
    } catch (error) {
      if (this.disposed || generation !== this.generation) return;
      this.phase = readFailure(error);
    }
  };

  get parent(): BreadcrumbItem | undefined {
    const parent = this.path?.items.at(-2);
    return parent?.kind === 'directory' ? parent : undefined;
  }

  get atRoot(): boolean {
    return this.path?.complete === true && this.path.items.length === 1 && this.path.items[0].kind === 'directory';
  }

  label = (item: BreadcrumbItem): string => this.path?.complete && this.path.items[0].id === item.id ? 'Files' : item.name;

  href = (item: BreadcrumbItem): string => this.path?.complete && this.path.items[0].id === item.id ? '/files' : '/files?node=' + encodeURIComponent(item.id);

  get visibleItems(): BreadcrumbItem[] {
    const items = this.path?.items ?? [];
    return items.length > 4 ? [items[0], ...items.slice(-2)] : items;
  }

  get omittedAncestors(): BreadcrumbItem[] {
    const items = this.path?.items ?? [];
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
