import type { FilesystemSettings, FilesystemSettingsPatch } from '#lib/admin/system-settings/domain/filesystem-settings.js';
import type { FilesystemSettingsAdministration } from '#lib/admin/system-settings/filesystem-settings-port.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';

type Approval = FilesystemSettings['require_mcp_file_deletion_approval'];
type Draft = FilesystemSettingsPatch['require_mcp_file_deletion_approval'];
type Failure = { kind: 'read' | 'write' | 'access'; message: string };

const sourceLabels: Record<Approval['source'], string> = {
  admin_override: 'Admin override',
  deployment_default: 'Deployment default',
  built_in_default: 'Built-in default'
};

export class FilesystemSettingsState {
  #saved = $state.raw<Readonly<Approval> | null>(null);
  #draft = $state.raw<Draft | null>(null);
  #failure = $state.raw<Failure | null>(null);
  #pending = $state.raw<AbortController | null>(null);

  constructor(private readonly settings: FilesystemSettingsAdministration) {}

  get ready(): boolean { return this.#saved !== null; }
  get busy(): boolean { return this.#pending !== null; }
  get loading(): boolean { return !this.ready && this.#failure === null; }
  get dirty(): boolean { return this.#draft !== null; }
  get resetting(): boolean { return this.#draft?.operation === 'reset'; }
  get checked(): boolean { return this.#draft?.operation === 'set' ? this.#draft.value : (this.#saved?.value ?? false); }
  get canReset(): boolean { return this.#saved?.source === 'admin_override' && !this.resetting; }
  get sourceLabel(): string { return this.#saved ? sourceLabels[this.#saved.source] : ''; }
  get failure(): string | undefined { return this.#failure?.message; }
  get canRetry(): boolean { return this.#failure?.kind === 'read'; }
  get canNavigateToProtectedSettings(): boolean { return !this.loading && this.#failure?.kind !== 'access'; }

  load = async (): Promise<void> => {
    if (this.busy || this.ready) return;
    await this.#request((signal): Promise<FilesystemSettings> => this.settings.get(signal), 'read');
  };

  change(value: boolean): void {
    if (this.busy || this.resetting || !this.#saved) return;
    this.#draft = value === this.#saved.value ? null : { operation: 'set', value };
    this.#failure = null;
  }

  reset = (): void => {
    if (this.busy || !this.canReset) return;
    this.#draft = { operation: 'reset' };
    this.#failure = null;
  };

  discard = (): void => {
    if (this.busy) return;
    this.#draft = null;
    this.#failure = null;
  };

  save = async (): Promise<void> => {
    const draft = this.#draft;
    if (this.busy || draft === null) return;
    await this.#request((signal): Promise<FilesystemSettings> => this.settings.update({
      require_mcp_file_deletion_approval: draft
    }, signal), 'write');
  };

  dispose = (): void => {
    this.#pending?.abort();
    this.#pending = null;
  };

  async #request(send: (signal: AbortSignal) => Promise<FilesystemSettings>, kind: 'read' | 'write'): Promise<void> {
    const controller = new AbortController();
    this.#pending = controller;
    this.#failure = null;
    try {
      const result = await send(controller.signal);
      if (controller.signal.aborted) return;
      this.#saved = result.require_mcp_file_deletion_approval;
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
      this.#failure = {
        kind: 'access',
        message: error instanceof AuthenticationRequiredError
          ? 'Sign in again to access system settings.'
          : 'You do not have permission to access system settings.'
      };
      return;
    }
    this.#failure = {
      kind,
      message: kind === 'read'
        ? 'Could not load filesystem settings.'
        : 'Could not confirm that your changes were saved. Try again.'
    };
  }
}
