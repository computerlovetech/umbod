import { SvelteMap } from 'svelte/reactivity';
import type { NodeSharingApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { nodeAccessSchema } from '../domain/sharing';
import { SharingDialogState } from './sharing-dialog-state.svelte';

export class SharingEligibilityState {
  private readonly allowed = new SvelteMap<string, boolean>();
  private readonly submitted = new Set<string>();
  private readonly controllers = new Map<string, AbortController>();
  private readonly versions = new Map<string, symbol>();
  private queue: string[] = [];
  private generation = 0;
  private active = 0;
  private disposed = false;
  readonly dialog: SharingDialogState;

  constructor(private readonly api: NodeSharingApi) {
    this.dialog = new SharingDialogState(api, this.revoke, this.recheck);
  }

  available = (id: string): boolean => this.allowed.get(id) === true;

  selectCurrent = (node: NodeSummary): void => {
    if (this.disposed || this.submitted.has(node.id)) return;
    this.submitted.add(node.id);
    void this.check(node.id, this.generation);
  };

  select = (nodes: readonly NodeSummary[]): void => {
    if (this.disposed) return;
    for (const node of nodes) {
      if (this.submitted.has(node.id)) continue;
      this.submitted.add(node.id);
      this.queue.push(node.id);
    }
    this.drain();
  };

  revoke = (id: string): void => {
    this.allowed.delete(id);
    this.controllers.get(id)?.abort();
    this.versions.delete(id);
  };

  remove = (id: string): void => {
    this.revoke(id);
    this.queue = this.queue.filter((candidate) => candidate !== id);
    this.submitted.delete(id);
    if (this.dialog.node?.id === id) this.dialog.reset();
  };

  recheck = (id: string): void => {
    if (this.disposed) return;
    this.revoke(id);
    this.queue.push(id);
    this.drain();
  };

  reset = (): void => {
    ++this.generation;
    for (const controller of this.controllers.values()) controller.abort();
    this.controllers.clear();
    this.versions.clear();
    this.allowed.clear();
    this.submitted.clear();
    this.queue = [];
    this.active = 0;
    this.dialog.reset();
  };

  dispose = (): void => { this.disposed = true; this.reset(); this.dialog.dispose(); };

  private drain(): void {
    while (!this.disposed && this.active < 4 && this.queue.length) {
      const id = this.queue.shift()!;
      ++this.active;
      const generation = this.generation;
      void this.check(id, generation).finally(() => {
        if (this.disposed || generation !== this.generation) return;
        --this.active;
        this.drain();
      });
    }
  }

  private async check(id: string, generation: number): Promise<void> {
    const controller = new AbortController();
    const version = Symbol();
    this.controllers.set(id, controller);
    this.versions.set(id, version);
    try {
      const access = nodeAccessSchema.parse(await this.api.inspectAccess(id, controller.signal));
      if (this.disposed || generation !== this.generation || this.versions.get(id) !== version || controller.signal.aborted) return;
      if (access.node_id === id) this.allowed.set(id, true);
    } catch {
      if (!this.disposed && generation === this.generation && this.versions.get(id) === version) this.allowed.delete(id);
    } finally {
      if (this.controllers.get(id) === controller) this.controllers.delete(id);
    }
  }
}
