import type { NodeSummary } from '$lib/files/domain/schemas';

export class NodeDetailsInputs {
  private current = $state.raw<NodeSummary>();

  constructor(node: NodeSummary) { this.current = node; }

  get node(): NodeSummary | undefined { return this.current; }

  select = (node: NodeSummary): void => { this.current = node; };
}
