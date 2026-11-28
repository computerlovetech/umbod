import { createContext } from 'svelte';

import type { ExistingSetupKind, UnifiedConnectorKind } from '#lib/admin/unified-connectors.js';

export type ConnectorSetupKind = UnifiedConnectorKind;

type ConnectorSetupEntry = {
  nativeAvailable: () => boolean;
  nativeUnavailable: () => boolean;
  disabled: () => boolean;
} & (
  | { kind: ExistingSetupKind; create: (trigger: HTMLButtonElement) => void }
  | { kind: 'portable' }
);

export const [getAddConnector, provideAddConnector] = createContext<AddConnectorState>();

export class AddConnectorState {
  #entry = $state.raw<ConnectorSetupEntry>();
  #open = $state(false);
  #handingOff = $state(false);
  #kind = $state<ConnectorSetupKind>();
  #choosingPortable = $state(false);
  #trigger: HTMLButtonElement | undefined;

  get open(): boolean { return this.#open; }
  get handingOff(): boolean { return this.#handingOff; }
  get kind(): ConnectorSetupKind | undefined { return this.#kind; }
  get trigger(): HTMLButtonElement | undefined { return this.#trigger; }
  get choosingPortable(): boolean { return this.#choosingPortable; }

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
    this.#choosingPortable = false;
    this.#open = true;
  };

  select = (kind: ConnectorSetupKind): void => {
    this.#kind = kind;
  };

  reopen = (kind: ConnectorSetupKind): void => {
    this.select(kind);
    this.#choosingPortable = false;
    this.#open = true;
  };

  choosePortable = (): void => {
    this.#choosingPortable = true;
  };

  backToType = (): void => {
    this.#choosingPortable = false;
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
