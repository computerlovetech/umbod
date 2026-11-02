import type { DescriptionState } from '$lib/files/state/description-state.svelte';
import type { NodeUpdateState } from '$lib/files/state/node-update-state.svelte';
import type { NodeSummary } from '$lib/files/domain/schemas';
import type { SharingEligibilityState } from '$lib/files/state/sharing-eligibility-state.svelte';
import type { DeletionState } from '$lib/files/state/deletion-state.svelte';

export class NodeActionsState {
  private expanded = $state(false);
  private element: HTMLElement | undefined;
  private fallbackFocus: HTMLElement | null = null;

  constructor(private readonly inputs: () => { update: NodeUpdateState; description: DescriptionState; node?: NodeSummary; sharing?: SharingEligibilityState; deletion?: DeletionState }) {}

  get open(): boolean { return this.expanded; }
  get available(): boolean {
    const { update, description } = this.inputs();
    return this.canShare || this.inputs().deletion?.available === true || this.inputs().deletion?.pending === true || update.canRename || update.canMove || update.probeFailed || update.needsReload || description.available || description.eligibility === 'error' || description.eligibility === 'sign-in' || description.needsReload;
  }
  get busy(): boolean { return this.inputs().update.pending || this.inputs().description.pending || this.inputs().deletion?.pending === true; }
  get canShare(): boolean {
    const { node, sharing } = this.inputs();
    return !!node && sharing?.available(node.id) === true;
  }

  share = (): void => {
    const { node, sharing } = this.inputs();
    if (!node || !sharing || !this.canShare || this.busy) return;
    this.run(() => sharing.dialog.show(node, this.element?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]') ?? undefined));
  };

  attach = (element: HTMLElement): (() => void) => {
    this.element = element;
    this.fallbackFocus = element.ownerDocument.getElementById('files-heading');
    return (): void => { this.element = undefined; };
  };

  restoreAfterDialog = (_element: HTMLElement): (() => void) => (): void => {
    queueMicrotask((): void => {
      const trigger = this.element?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
      if (trigger?.isConnected) trigger.focus();
      else if (this.fallbackFocus?.isConnected) this.fallbackFocus.focus();
    });
  };

  setOpen = (open: boolean): void => { this.expanded = open; };

  run = (action: () => unknown): void => {
    this.expanded = false;
    this.element?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')?.focus();
    action();
  };
}
