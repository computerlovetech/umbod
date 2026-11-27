import { untrack } from 'svelte';

export class DisclosureState {
  #expanded: boolean;
  private trigger: HTMLButtonElement | undefined;
  private panel: HTMLDivElement | undefined;

  constructor(
    initiallyOpen: boolean,
    private readonly controlledExpanded: () => boolean | undefined,
    private readonly onOpenChange: (open: boolean) => void
  ) {
    this.#expanded = $state(initiallyOpen);
  }

  get expanded(): boolean {
    return this.controlledExpanded() ?? this.#expanded;
  }

  attachTrigger = (trigger: HTMLButtonElement): (() => void) => {
    this.trigger = trigger;
    return (): void => { this.trigger = undefined; };
  };

  attachPanel = (panel: HTMLDivElement): (() => void) => {
    this.panel = panel;
    return (): void => { this.panel = undefined; };
  };

  toggle = (): void => {
    this.setExpanded(!untrack(() => this.expanded));
  };

  open = (): void => {
    this.setExpanded(true);
  };

  close = (): void => {
    this.setExpanded(false);
  };

  restoreFocus = (): void => {
    if (this.trigger?.isConnected && this.panel?.contains(this.trigger.ownerDocument.activeElement)) {
      this.trigger.focus();
    }
  };

  private setExpanded(expanded: boolean): void {
    untrack((): void => {
      if (this.expanded === expanded) return;
      if (this.controlledExpanded() === undefined) this.#expanded = expanded;
      this.onOpenChange(expanded);
      if (!expanded && !this.expanded) this.restoreFocus();
    });
  }
}
