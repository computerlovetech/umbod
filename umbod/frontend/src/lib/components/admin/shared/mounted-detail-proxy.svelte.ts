import { SvelteMap } from 'svelte/reactivity';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';

export type MountedDetailLoader<Detail> = (id: string, signal?: AbortSignal) => Promise<Detail>;

export type MountedDetailProxyOptions<Detail> = {
  selectedId?: string | null;
  initialDetail?: Detail;
  initialDetailFailed?: boolean;
  loadDetail?: MountedDetailLoader<Detail>;
};

export class MountedDetailProxy<Detail> {
  selectedId = $state<string | null>(null);
  mounted = $state.raw<Detail | null>(null);
  loading = $state(false);
  failed = $state(false);
  private readonly cache = new SvelteMap<string, Detail>();
  private readonly loader: MountedDetailLoader<Detail> | null;
  private controller: AbortController | null = null;
  private activeRequest: { id: string; promise: Promise<Detail | null> } | null = null;
  private generation = 0;
  private readonly requestVersions = new Map<string, number>();

  constructor(options: MountedDetailProxyOptions<Detail> = {}) {
    this.selectedId = options.selectedId ?? null;
    this.loader = options.loadDetail ?? null;
    if (options.initialDetail !== undefined && this.selectedId !== null) {
      this.cache.set(this.selectedId, options.initialDetail);
      this.mounted = options.initialDetail;
    }
    this.failed = options.initialDetailFailed ?? false;
  }

  select = (id: string): void => {
    this.selectedId = id;
    const cached = this.cache.get(id);
    if (cached !== undefined) {
      this.controller?.abort();
      this.generation += 1;
      this.mounted = cached;
      this.loading = false;
      this.failed = false;
      return;
    }
    this.mounted = null;
    void this.getOrLoad(id);
  };

  ensure = (): void => {
    if (this.selectedId !== null && !this.loading && this.cache.get(this.selectedId) === undefined) void this.getOrLoad(this.selectedId);
  };

  retry = (): void => {
    if (this.selectedId !== null) void this.load(this.selectedId);
  };

  fetch = async (id: string): Promise<Detail | null> => {
    this.selectedId = id;
    return this.load(id);
  };

  getOrLoad = (id: string): Promise<Detail | null> => {
    const cached = this.cache.get(id);
    if (cached !== undefined) return Promise.resolve(cached);
    if (this.activeRequest?.id === id) return this.activeRequest.promise;
    const promise = this.load(id);
    this.activeRequest = { id, promise };
    void promise.finally(() => {
      if (this.activeRequest?.promise === promise) this.activeRequest = null;
    });
    return promise;
  };

  read = (id: string): Detail | undefined => this.cache.get(id);

  synchronize = (selectedId: string | null | undefined, detail?: Detail, failed = false): void => {
    this.controller?.abort();
    this.controller = null;
    this.generation += 1;
    this.selectedId = selectedId ?? null;
    this.loading = false;
    this.failed = failed;
    if (this.selectedId === null) {
      this.mounted = null;
      return;
    }
    this.requestVersions.set(this.selectedId, (this.requestVersions.get(this.selectedId) ?? 0) + 1);
    if (detail === undefined) {
      this.cache.delete(this.selectedId);
      this.mounted = null;
      return;
    }
    this.cache.set(this.selectedId, detail);
    this.mounted = detail;
    this.failed = false;
  };

  update = (id: string, reconcile: (detail: Detail) => Detail): void => {
    const current = this.cache.get(id);
    if (current === undefined) return;
    const updated = reconcile(current);
    this.cache.set(id, updated);
    if (this.selectedId === id) this.mounted = updated;
  };

  private load = async (id: string): Promise<Detail | null> => {
    if (this.loader === null) return null;
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    const generation = ++this.generation;
    const requestVersion = (this.requestVersions.get(id) ?? 0) + 1;
    this.requestVersions.set(id, requestVersion);
    this.loading = true;
    this.failed = false;
    try {
      const detail = await this.loader(id, controller.signal);
      if (this.requestVersions.get(id) === requestVersion) {
        this.cache.set(id, detail);
        if (generation === this.generation && this.selectedId === id) this.mounted = detail;
      }
      return detail;
    } catch (error) {
      if (controller.signal.aborted) return null;
      if (!(error instanceof BrowserRequestError)) throw error;
      if (generation === this.generation && this.selectedId === id) this.failed = true;
      return null;
    } finally {
      if (generation === this.generation) this.loading = false;
    }
  };
}
