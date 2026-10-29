import { tick } from 'svelte';
import { SvelteMap } from 'svelte/reactivity';
import type { FilesApi } from '../api';
import type { NodeSummary } from '../domain/schemas';
import { DeletionState } from './deletion-state.svelte';

export class RowDeletionState {
  readonly controllers = new SvelteMap<string, DeletionState>();
  private readonly buttons = new Map<string, HTMLButtonElement>();
  private readonly recoveryControls = new Map<string, HTMLElement>();
  private readonly submittedIds = new Set<string>();
  private queue: NodeSummary[] = [];
  private activeChecks = 0;
  private generation = 0;
  private disposed = false;
  private focusAfterRemoval: () => void = () => {};

  constructor(private readonly api: FilesApi, private readonly reload: () => Promise<void>, private readonly onDeleted: (node: NodeSummary) => void, private readonly operations: SvelteMap<string, symbol>) {}

  attachFocus = (heading: HTMLElement): (() => void) => {
    this.focusAfterRemoval = (): void => heading.focus();
    return (): void => { this.focusAfterRemoval = (): void => {}; };
  };

  attachButton = (id: string): ((button: HTMLButtonElement) => () => void) => (button) => {
    this.buttons.set(id, button);
    return (): void => { if (this.buttons.get(id) === button) this.buttons.delete(id); };
  };

  attachRecovery = (id: string): ((control: HTMLElement) => () => void) => (control) => {
    this.recoveryControls.set(id, control);
    return (): void => { if (this.recoveryControls.get(id) === control) this.recoveryControls.delete(id); };
  };

  confirm = async (id: string): Promise<void> => {
    const generation = this.generation;
    const controller = this.controllers.get(id);
    if (!controller?.confirmation || controller.pending) return;
    await controller.confirm();
    await tick();
    if (!this.disposed && generation === this.generation && controller.needsReload && controller.message) {
      this.recoveryControls.get(id)?.focus();
    }
  };

  cancel = async (id: string): Promise<void> => {
    const generation = this.generation;
    this.controllers.get(id)?.cancel();
    await tick();
    if (!this.disposed && generation === this.generation) this.buttons.get(id)?.focus();
  };

  reset = (): void => {
    ++this.generation;
    this.queue = [];
    this.activeChecks = 0;
    this.submittedIds.clear();
    for (const controller of this.controllers.values()) controller.reset();
  };

  select = (nodes: NodeSummary[]): void => {
    if (this.disposed) return;
    for (const node of nodes) {
      if (node.kind !== 'file' || typeof node.parent_id !== 'string' || this.submittedIds.has(node.id)) continue;
      this.submittedIds.add(node.id);
      this.queue.push(node);
    }
    this.drain();
  };

  private drain = (): void => {
    while (!this.disposed && this.activeChecks < 4 && this.queue.length > 0) {
      const node = this.queue.shift()!;
      let controller = this.controllers.get(node.id);
      if (!controller) {
        controller = new DeletionState(this.api, this.refresh, this.reload, this.onDeleted, false, this.operations);
        this.controllers.set(node.id, controller);
      }
      ++this.activeChecks;
      void this.check(controller, node, this.generation);
    }
  };

  private check = async (controller: DeletionState, node: NodeSummary, generation: number): Promise<void> => {
    await controller.select(node);
    if (this.disposed || generation !== this.generation) return;
    --this.activeChecks;
    this.drain();
  };

  private refresh = async (): Promise<void> => {
    const expectedGeneration = this.generation + 1;
    await this.reload();
    if (!this.disposed && this.generation === expectedGeneration) this.focusAfterRemoval();
  };

  dispose = (): void => {
    this.disposed = true;
    this.reset();
    for (const controller of this.controllers.values()) controller.dispose();
    this.controllers.clear();
  };
}
