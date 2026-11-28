import type { PortableConnectorSettings } from '#lib/admin/system-settings/domain/portable-connector-settings.js';
import type { PortableConnectorSettingsAdministration } from '#lib/admin/system-settings/portable-connector-settings-port.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';

type Failure = { kind: 'read' | 'write' | 'access'; message: string };

export class PortableConnectorSettingsState {
  #saved = $state<boolean | null>(null);
  #draft = $state<boolean | null>(null);
  #pending = $state.raw<AbortController | null>(null);
  #failure = $state.raw<Failure | null>(null);

  constructor(private readonly settings: PortableConnectorSettingsAdministration) {}

  get ready(): boolean { return this.#saved !== null; }
  get busy(): boolean { return this.#pending !== null; }
  get loading(): boolean { return !this.ready && this.#failure === null; }
  get dirty(): boolean { return this.#draft !== null; }
  get checked(): boolean { return this.#draft ?? this.#saved ?? false; }
  get allowed(): boolean { return this.#failure?.kind !== 'access'; }
  get canRetry(): boolean { return this.#failure?.kind === 'read'; }
  get failure(): string | undefined { return this.#failure?.message; }

  load = async (): Promise<void> => {
    if (this.busy || this.ready || !this.allowed) return;
    await this.#request((signal): Promise<PortableConnectorSettings> => this.settings.get(signal), 'read');
  };

  change = (enabled: boolean): void => {
    if (this.busy || !this.ready) return;
    this.#draft = enabled === this.#saved ? null : enabled;
    this.#failure = null;
  };

  discard = (): void => {
    if (this.busy || !this.ready) return;
    this.#draft = null;
    this.#failure = null;
  };

  save = async (): Promise<void> => {
    const enabled = this.#draft;
    if (this.busy || enabled === null) return;
    await this.#request((signal): Promise<PortableConnectorSettings> => this.settings.update({ enabled }, signal), 'write');
  };

  dispose = (): void => {
    this.#pending?.abort();
    this.#pending = null;
  };

  async #request(send: (signal: AbortSignal) => Promise<PortableConnectorSettings>, kind: 'read' | 'write'): Promise<void> {
    const controller = new AbortController();
    this.#pending = controller;
    this.#failure = null;
    try {
      const result = await send(controller.signal);
      if (controller.signal.aborted) return;
      this.#saved = result.enabled;
      this.#draft = null;
    } catch (error) {
      if (!controller.signal.aborted) this.#recordFailure(error, kind);
    } finally {
      if (!controller.signal.aborted) this.#pending = null;
    }
  }

  #recordFailure(error: unknown, kind: 'read' | 'write'): void {
    if (error instanceof AuthenticationRequiredError || (error instanceof HttpError && error.status === 403)) {
      this.#saved = null;
      this.#draft = null;
      this.#failure = { kind: 'access', message: 'Administration access is no longer available. Reload or sign in again.' };
      return;
    }
    this.#failure = {
      kind,
      message: kind === 'read'
        ? 'Could not load portable connector settings.'
        : 'Could not confirm that your changes were saved. Try again.'
    };
  }
}
