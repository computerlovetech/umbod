import { createContext } from 'svelte';

import type { UnifiedConnectorKind } from '#lib/admin/unified-connectors.js';

export type ConnectorSetupKind = UnifiedConnectorKind;

type ConnectorSetupEntry = {
  kind: ConnectorSetupKind;
  nativeAvailable: () => boolean;
  nativeUnavailable: () => boolean;
  disabled: () => boolean;
  create: (trigger: HTMLButtonElement) => void;
};

export const [getAddConnector, provideAddConnector] = createContext<AddConnectorState>();

export class AddConnectorState {
  #entry = $state.raw<ConnectorSetupEntry>();
  #open = $state(false);
  #handingOff = $state(false);
  #kind = $state<ConnectorSetupKind>();
  #trigger: HTMLButtonElement | undefined;

  get open(): boolean { return this.#open; }
  get handingOff(): boolean { return this.#handingOff; }
  get kind(): ConnectorSetupKind | undefined { return this.#kind; }
  get trigger(): HTMLButtonElement | undefined { return this.#trigger; }

  get entry(): ConnectorSetupEntry | undefined { return this.#entry; }

  registerSetup = (entry: ConnectorSetupEntry): (() => void) => {
    this.#entry = entry;
    return (): void => { if (this.#entry === entry) this.#entry = undefined; };
  };

  register = (trigger: HTMLButtonElement): (() => void) => {
    this.#trigger = trigger;
    return (): void => { if (this.#trigger === trigger) this.#trigger = undefined; };
  };

  show = (): void => {
    this.#kind = undefined;
    this.#open = true;
  };

  select = (kind: ConnectorSetupKind): void => {
    this.#kind = kind;
  };

  reopen = (kind: ConnectorSetupKind): void => {
    this.select(kind);
    this.#open = true;
  };

  beginHandoff(): void {
    this.#handingOff = true;
  }

  endHandoff(): void {
    this.#handingOff = false;
  }

  close = (): void => {
    this.#open = false;
  };
}
