import { SvelteMap } from 'svelte/reactivity';
import type { FilesystemApi } from '../api';
import type { BrowseCapabilities, NodeSummary } from '../domain/schemas';
import { NodeUpdateState } from './node-update-state.svelte';
import { DescriptionState } from './description-state.svelte';

export class RowEditingEntry {
  readonly update: NodeUpdateState;
  readonly description: DescriptionState;

  constructor(api: FilesystemApi, accept: (node: NodeSummary) => void, reload: () => Promise<void>, personalRoot: () => string | undefined = () => undefined) {
    this.update = new NodeUpdateState(api, accept, reload, personalRoot);
    this.description = new DescriptionState(api, accept, reload);
  }
}

export class RowEditingState {
  readonly controllers = new SvelteMap<string, RowEditingEntry>();
  private readonly nodes = new Map<string, NodeSummary>();
  private queue: { id: string; operation: 'update' | 'description' }[] = [];
  private activeChecks = 0;
  private generation = 0;
  private disposed = false;

  constructor(private readonly api: FilesystemApi, private readonly accept: (node: NodeSummary) => void, private readonly reload: () => Promise<void>, private readonly personalRoot: () => string | undefined = () => undefined) {}

  select = (nodes: NodeSummary[], capabilities?: ReadonlyMap<string, BrowseCapabilities>): void => {
    if (this.disposed) return;
    for (const node of nodes) {
      let entry = this.controllers.get(node.id);
      if (!entry) {
        entry = new RowEditingEntry(this.api, this.accept, async (): Promise<void> => {
          if (this.disposed) return;
          const generation = this.generation + 1;
          await this.reload();
          if (this.disposed || generation !== this.generation) return;
          const refreshed = this.nodes.get(node.id);
          if (refreshed) this.controllers.get(node.id)?.update.acceptReloadedNode(refreshed);
        }, this.personalRoot);
        this.controllers.set(node.id, entry);
      }
      const previous = this.nodes.get(node.id);
      if (previous) {
        if (node.revision < previous.revision) continue;
        this.nodes.set(node.id, node);
        entry.update.acceptUpdatedNode(node);
        entry.description.acceptUpdatedNode(node);
      } else {
        this.nodes.set(node.id, node);
        const eligibility = capabilities?.get(node.id);
        if (eligibility) {
          void entry.update.select(node, eligibility);
          void entry.description.select(node, eligibility.edit_description);
        } else this.queue.push({ id: node.id, operation: 'update' }, { id: node.id, operation: 'description' });
      }
    }
    this.drain();
  };

  private drain = (): void => {
    while (!this.disposed && this.activeChecks < 4 && this.queue.length > 0) {
      const { id, operation } = this.queue.shift()!;
      const entry = this.controllers.get(id)!;
      ++this.activeChecks;
      void this.check(entry[operation], this.nodes.get(id)!, this.generation);
    }
  };

  private check = async (controller: NodeUpdateState | DescriptionState, node: NodeSummary, generation: number): Promise<void> => {
    await controller.select(node);
    if (this.disposed || generation !== this.generation) return;
    --this.activeChecks;
    this.drain();
  };

  reset = (): void => {
    ++this.generation;
    this.queue = [];
    this.activeChecks = 0;
    this.nodes.clear();
    for (const entry of this.controllers.values()) {
      entry.update.reset();
      entry.description.reset();
    }
  };

  dispose = (): void => {
    this.disposed = true;
    this.reset();
    for (const entry of this.controllers.values()) {
      entry.update.dispose();
      entry.description.dispose();
    }
    this.controllers.clear();
  };
}
