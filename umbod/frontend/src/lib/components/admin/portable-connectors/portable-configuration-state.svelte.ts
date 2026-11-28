import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import type { PortableConnectorConfiguration, PortableConnectorField } from '#lib/admin/portable-connectors/domain/schemas.js';
import type { PortableConnectors } from '#lib/admin/portable-connectors/port.js';
import { portableRow, type PortableConnectorRow } from '#lib/admin/unified-connectors.js';

type ConfigurationApi = Pick<PortableConnectors, 'getConfiguration' | 'replaceConfiguration'>;
type SaveStatus = 'idle' | 'saving' | 'saved' | 'save-error' | 'write-unconfirmed';
type ConfigurationState =
  | { status: 'loading' | 'load-error' }
  | { status: 'ready'; detail: PortableConnectorConfiguration; save: SaveStatus };

function fieldError(field: PortableConnectorField, value: string | undefined): string | undefined {
  if (value === undefined) return field.required ? `${field.label} is required.` : undefined;
  if (field.choices.length && !field.choices.includes(value)) return `Choose an option for ${field.label}.`;
  const length = [...value].length;
  if (length < field.min_length) return `${field.label} must have at least ${field.min_length} characters.`;
  if (length > field.max_length) return `${field.label} must have at most ${field.max_length} characters.`;
  return undefined;
}

function isDenied(error: unknown): boolean {
  return error instanceof AuthenticationRequiredError || (error instanceof HttpError && error.status === 403);
}

export class PortableConfigurationState {
  #configuration = $state.raw<ConfigurationState>({ status: 'loading' });
  #draft = $state.raw<Readonly<Record<string, string>>>({});
  #submitted = $state(false);
  #request: AbortController | undefined;

  constructor(private readonly initial: PortableConnectorRow, private readonly api: ConfigurationApi) {}

  get status(): ConfigurationState['status'] { return this.#configuration.status; }

  get connector(): PortableConnectorRow {
    return this.#configuration.status === 'ready' ? portableRow(this.#configuration.detail.connector) : this.initial;
  }

  get saveStatus(): SaveStatus {
    return this.#configuration.status === 'ready' ? this.#configuration.save : 'idle';
  }

  get editingDisabled(): boolean { return this.saveStatus === 'saving' || this.saveStatus === 'write-unconfirmed'; }

  get fields(): readonly Readonly<PortableConnectorField>[] {
    return this.#configuration.status === 'ready' ? this.#configuration.detail.fields : [];
  }

  value(field: PortableConnectorField): string | undefined {
    if (Object.hasOwn(this.#draft, field.name)) return this.#draft[field.name];
    return field.required && !field.choices.length ? '' : undefined;
  }

  errorFor(field: PortableConnectorField): string | undefined {
    return this.#submitted ? fieldError(field, this.value(field)) : undefined;
  }

  change = (field: PortableConnectorField, value: string | undefined): void => {
    if (this.#configuration.status !== 'ready' || this.editingDisabled) return;
    const { [field.name]: _, ...remaining } = this.#draft;
    this.#draft = value === undefined ? remaining : { ...remaining, [field.name]: value };
    this.#configuration = { ...this.#configuration, save: 'idle' };
  };

  load = async (): Promise<void> => {
    if (this.#request) return;
    const request = new AbortController();
    this.#request = request;
    this.#configuration = { status: 'loading' };
    try {
      const detail = await this.api.getConfiguration(this.initial.id, request.signal);
      if (!request.signal.aborted) this.#accept(detail, 'idle');
    } catch {
      if (!request.signal.aborted) this.#configuration = { status: 'load-error' };
    } finally {
      if (this.#request === request) this.#request = undefined;
    }
  };

  save = async (): Promise<void> => {
    const current = this.#configuration;
    if (current.status !== 'ready' || this.#request || this.editingDisabled) return;
    this.#submitted = true;
    if (this.fields.some((field) => this.errorFor(field))) return;
    const configuration = Object.fromEntries(this.fields.flatMap((field) => {
      const value = this.value(field);
      return value === undefined ? [] : [[field.name, value] as const];
    }));
    const request = new AbortController();
    this.#request = request;
    this.#configuration = { ...current, save: 'saving' };
    try {
      const detail = await this.api.replaceConfiguration(this.initial.id, { configuration }, request.signal);
      if (!request.signal.aborted) this.#accept(detail, 'saved');
    } catch (error) {
      if (!request.signal.aborted) {
        if (isDenied(error)) {
          this.#draft = {};
          this.#configuration = { status: 'load-error' };
        } else {
          const rejected = error instanceof HttpError && error.status >= 400 && error.status < 500;
          this.#configuration = { ...current, save: rejected ? 'save-error' : 'write-unconfirmed' };
        }
      }
    } finally {
      if (this.#request === request) this.#request = undefined;
    }
  };

  dispose = (): void => {
    this.#request?.abort();
    this.#request = undefined;
  };

  #accept(detail: PortableConnectorConfiguration, save: 'idle' | 'saved'): void {
    this.#draft = detail.configuration ?? {};
    this.#submitted = false;
    this.#configuration = { status: 'ready', detail, save };
  }
}
