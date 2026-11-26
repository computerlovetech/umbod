export class ReportingInstructionsState {
  #openId = $state<string | null>(null);

  isOpen(id: string): boolean {
    return this.#openId === id;
  }

  toggle(id: string): void {
    this.#openId = this.isOpen(id) ? null : id;
  }
}
