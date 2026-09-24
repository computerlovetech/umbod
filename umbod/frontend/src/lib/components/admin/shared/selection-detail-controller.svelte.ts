import { MountedDetailProxy, type MountedDetailLoader } from './mounted-detail-proxy.svelte';
import type { SelectionUrlPort } from './selection-url-port';

export type SelectionDetailControllerOptions<Item, Detail> = {
  items: Item[];
  itemId: (item: Item) => string;
  selectedId?: string | null;
  initialDetail?: Detail;
  initialDetailFailed?: boolean;
  loadDetail?: MountedDetailLoader<Detail>;
  url: SelectionUrlPort;
  onSelectionChange?: (selectedId: string) => void;
  allowUnknownSelection?: boolean;
};

export class SelectionDetailController<Item, Detail> {
  items = $state.raw<Item[]>([]);
  private readonly itemId: (item: Item) => string;
  private readonly url: SelectionUrlPort;
  private readonly onSelectionChange: ((selectedId: string) => void) | null;
  private readonly allowUnknownSelection: boolean;
  private readonly detailProxy: MountedDetailProxy<Detail>;

  get selectedId(): string | null { return this.detailProxy.selectedId; }
  get selectedItem(): Item | null { return this.items.find((item) => this.itemId(item) === this.selectedId) ?? this.items[0] ?? null; }
  get detail(): Detail | null { return this.detailProxy.mounted; }
  get loading(): boolean { return this.detailProxy.loading; }
  get failed(): boolean { return this.detailProxy.failed; }

  constructor(options: SelectionDetailControllerOptions<Item, Detail>) {
    this.items = options.items;
    this.itemId = options.itemId;
    this.url = options.url;
    this.onSelectionChange = options.onSelectionChange ?? null;
    this.allowUnknownSelection = options.allowUnknownSelection ?? false;
    const requestedId = options.selectedId ?? this.url.readSelection();
    const selectedId = this.acceptedId(requestedId) ?? this.firstId();
    this.detailProxy = new MountedDetailProxy({
      selectedId,
      initialDetail: options.initialDetail,
      initialDetailFailed: options.initialDetailFailed,
      loadDetail: options.loadDetail
    });
  }

  select = (selectedId: string): void => {
    if (this.acceptedId(selectedId) === null) return;
    if (this.selectedId === selectedId) {
      this.detailProxy.ensure();
      return;
    }
    this.onSelectionChange?.(selectedId);
    this.detailProxy.select(selectedId);
    this.url.replaceSelection(selectedId);
  };

  retry = (): void => this.detailProxy.retry();

  fetch = (selectedId: string): Promise<Detail | null> => {
    if (this.acceptedId(selectedId) === null) return Promise.resolve(null);
    return this.detailProxy.fetch(selectedId);
  };

  load = (selectedId: string): Promise<Detail | null> => {
    if (this.acceptedId(selectedId) === null) return Promise.resolve(null);
    return this.detailProxy.getOrLoad(selectedId);
  };

  readDetail = (selectedId: string): Detail | undefined => this.detailProxy.read(selectedId);

  updateDetail = (selectedId: string, reconcile: (detail: Detail) => Detail): void => {
    this.detailProxy.update(selectedId, reconcile);
  };

  replaceItems = (items: Item[]): void => {
    const hadItems = this.items.length > 0;
    this.items = items;
    if (this.validId(this.selectedId) !== null) return;
    if (!hadItems && this.selectedId !== null && this.allowUnknownSelection) return;
    const fallbackId = this.firstId();
    if (fallbackId !== null) this.detailProxy.select(fallbackId);
    else this.detailProxy.synchronize(null);
  };

  private acceptedId = (selectedId: string | null): string | null =>
    this.allowUnknownSelection && selectedId !== null ? selectedId : this.validId(selectedId);

  private validId = (selectedId: string | null): string | null =>
    selectedId !== null && this.items.some((item) => this.itemId(item) === selectedId) ? selectedId : null;

  private firstId = (): string | null => this.items[0] ? this.itemId(this.items[0]) : null;
}
