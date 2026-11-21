import { approvedHostnameSchema, importOpenApiCatalogUrlRequestSchema, normalizeToolNamePrefix, OPEN_API_CATALOG_FILE_MAX_BYTES } from '#lib/admin/openapi-connectors.js';
import type { ToastApi } from '#lib/components/feedback/index.js';
import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
import { isOperationalError } from '#lib/admin/infrastructure/transport.js';

export type OpenApiSetupMode = 'create' | 'configure';
export type OpenApiAuthenticationType = 'none' | 'bearer';
export type OpenApiImportMode = 'file' | 'url';

type Specification = Record<string, unknown>;

function objectRecord(value: unknown): Specification | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Specification : undefined;
}

function declaredServers(document: Specification): string[] | undefined {
  if (document.servers === undefined) return [];
  if (!Array.isArray(document.servers)) return undefined;
  const servers: string[] = [];
  for (const entry of document.servers as unknown[]) {
    const server = objectRecord(entry);
    const value = server?.url;
    if (!server || 'variables' in server || '$ref' in server || typeof value !== 'string' || !value.startsWith('https://') || /[{}]/.test(value)) return undefined;
    try {
      const url = new URL(value);
      if (!url.hostname || url.username || url.password) return undefined;
      servers.push(url.href);
    } catch {
      return undefined;
    }
  }
  return servers;
}

export class OpenApiConnectorSetupState {
  #step = $state<1 | 2 | 3>(1);
  #servers = $state<string[]>([]);
  #source: { kind: 'file'; file: File } | { kind: 'url'; document: string } | undefined;
  #sourceAttempt = 0;

  get step(): 1 | 2 | 3 { return this.#step; }
  get session(): number { return this.#sourceAttempt; }
  get servers(): readonly string[] { return [...new Set(this.#servers)]; }
  get hostnameValid(): boolean {
    const host = approvedHostnameSchema.safeParse(this.approvedHostname);
    return host.success && (!this.#servers.length || this.#servers.filter((server: string): boolean => new URL(server).hostname === host.data).length === 1);
  }
  open = $state(false);
  mode = $state<OpenApiSetupMode>('create');
  connectorId = $state('');
  displayName = $state('');
  toolNamePrefix = $state('connector');
  capabilityDescription = $state('');
  authenticationType = $state<OpenApiAuthenticationType>('none');
  approvedHostname = $state('');
  importMode = $state<OpenApiImportMode>('file');
  specificationUrl = $state('');
  urlError = $state('');
  configuredBearer = $state(false);
  submitting = $state(false);
  message = $state('');
  setupBlocked = $state(false);
  private returnFocus: HTMLElement | null = null;
  private toolNamePrefixEdited = false;
  #displayNameEdited = false;
  #descriptionEdited = false;

  constructor(
    private readonly request: typeof globalThis.fetch = globalThis.fetch,
    private readonly toast?: ToastApi
  ) {}

  showCreate = (trigger: HTMLElement): void => {
    this.#sourceAttempt++;
    this.submitting = false;
    this.#displayNameEdited = false;
    this.#descriptionEdited = false;
    this.mode = 'create';
    this.#step = 1;
    this.#source = undefined;
    this.#servers = [];
    this.setupBlocked = false;
    this.connectorId = '';
    this.displayName = '';
    this.toolNamePrefix = 'connector';
    this.toolNamePrefixEdited = false;
    this.capabilityDescription = '';
    this.authenticationType = 'none';
    this.approvedHostname = '';
    this.importMode = 'file';
    this.specificationUrl = '';
    this.urlError = '';
    this.configuredBearer = false;
    this.message = '';
    this.show(trigger);
  };

  showConfigure = async (trigger: HTMLElement, connectorId: string, displayName: string, toolNamePrefix: string, capabilityDescription: string): Promise<void> => {
    const session = ++this.#sourceAttempt;
    let configuration;
    try {
      configuration = await adminApi(this.request).openApiConnectors.connectors.getConfiguration(connectorId);
    } catch (cause) {
      if (session !== this.#sourceAttempt) return;
      if (!isOperationalError(cause)) throw cause;
      this.toast?.error('Bearer configuration could not be loaded. Try again.');
      return;
    }
    if (session !== this.#sourceAttempt) return;
    const configuredBearer = configuration.authentication_type === 'bearer' && configuration.configured;
    this.mode = 'configure';
    this.connectorId = connectorId;
    this.displayName = displayName;
    this.toolNamePrefix = toolNamePrefix;
    this.toolNamePrefixEdited = true;
    this.capabilityDescription = capabilityDescription;
    this.authenticationType = configuredBearer ? 'bearer' : 'none';
    this.configuredBearer = configuredBearer;
    this.approvedHostname = '';
    this.importMode = 'file';
    this.specificationUrl = '';
    this.urlError = '';
    this.message = '';
    this.show(trigger);
  };

  close = (): void => {
    this.#sourceAttempt++;
    this.#source = undefined;
    this.open = false;
    this.submitting = false;
    queueMicrotask(() => this.returnFocus?.focus());
  };

  handleKeydown = (event: KeyboardEvent): void => {
    if (!this.open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
      return;
    }
    if (event.key === 'Tab' && this.mode === 'configure') {
      const controls = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"] button, [role="dialog"] input, [role="dialog"] select')).filter((control) => !control.hasAttribute('disabled'));
      const first = controls.at(0);
      const last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  };

  setDisplayName = (event: Event): void => {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    this.#displayNameEdited = true;
    this.displayName = event.currentTarget.value;
    if (!this.toolNamePrefixEdited) this.toolNamePrefix = normalizeToolNamePrefix(this.displayName);
  };

  setToolNamePrefix = (event: Event): void => {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    this.toolNamePrefix = event.currentTarget.value;
    this.toolNamePrefixEdited = true;
  };

  setCapabilityDescription = (event: Event): void => {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    this.#descriptionEdited = true;
    this.capabilityDescription = event.currentTarget.value;
  };

  setAuthentication = (value: string): void => {
    this.authenticationType = value as OpenApiAuthenticationType;
  };

  setHostname = (event: Event): void => {
    if (event.currentTarget instanceof HTMLInputElement) this.approvedHostname = event.currentTarget.value;
  };

  setImportMode = (mode: OpenApiImportMode): void => {
    this.importMode = mode;
    this.urlError = '';
    this.message = '';
  };

  setSpecificationUrl = (event: Event): void => {
    if (event.currentTarget instanceof HTMLInputElement) this.replaceSpecificationUrl(event.currentTarget.value);
  };

  replaceSpecificationUrl = (value: string): void => {
    this.specificationUrl = value;
    this.urlError = '';
  };

  reviewSource = async (formData: FormData): Promise<void> => {
    if (!this.open || this.mode !== 'create' || this.#step !== 1 || this.submitting) return;
    const attempt = ++this.#sourceAttempt;
    this.beginSubmit();
    this.urlError = '';
    let document: Specification | undefined;
    if (this.importMode === 'url') {
      if (await this.prepareSource(formData, () => attempt === this.#sourceAttempt)) {
        document = objectRecord(JSON.parse(String(formData.get('document'))));
      }
    } else {
      formData.set('importMode', 'file');
      const file = formData.get('file');
      if (file instanceof File && file.name.toLowerCase().endsWith('.json') && file.type === 'application/json' && file.size <= OPEN_API_CATALOG_FILE_MAX_BYTES) {
        try { document = objectRecord(JSON.parse(await file.text())); } catch { document = undefined; }
      }
    }
    if (attempt !== this.#sourceAttempt) return;
    this.submitting = false;
    const info = objectRecord(document?.info);
    if (!document || !info || !objectRecord(document.paths) || typeof document.openapi !== 'string' || !/^3\.[01]\./.test(document.openapi)) {
      this.urlError ||= 'Choose an OpenAPI 3.0 or 3.1 JSON specification with info and paths (up to 10 MB).';
      return;
    }
    const servers = declaredServers(document);
    if (!servers) {
      this.urlError = 'Use absolute HTTPS server URLs without credentials or variables in the specification.';
      return;
    }
    const file = formData.get('file');
    this.#source = file instanceof File ? { kind: 'file', file } : { kind: 'url', document: String(formData.get('document')) };
    this.#servers = servers;
    this.approvedHostname = servers.length === 1 ? new URL(servers[0]).hostname : '';
    if (!this.#displayNameEdited) {
      this.displayName = typeof info.title === 'string' ? info.title.trim().slice(0, 200) : '';
      if (!this.toolNamePrefixEdited) this.toolNamePrefix = normalizeToolNamePrefix(this.displayName);
    }
    if (!this.#descriptionEdited) this.capabilityDescription = typeof info.description === 'string' ? info.description.trim().slice(0, 300) : '';
    this.#step = 2;
  };

  confirmHostname = (): void => {
    if (this.#step === 2 && this.hostnameValid && !this.setupBlocked) this.#step = 3;
  };

  back = (): void => {
    if (this.submitting || this.setupBlocked) return;
    if (this.#step === 3) this.#step = 2;
    else if (this.#step === 2) this.#step = 1;
    this.message = '';
  };

  prepareSubmission = async (formData: FormData): Promise<boolean> => {
    if (this.mode === 'configure') return this.prepareSource(formData, () => this.open);
    if (this.#step !== 3 || !this.hostnameValid || !this.#source || this.setupBlocked) return false;
    formData.set('importMode', this.#source.kind);
    if (this.#source.kind === 'file') formData.set('file', this.#source.file);
    else formData.set('document', this.#source.document);
    formData.set('approvedHostname', this.approvedHostname);
    return true;
  };

  private async prepareSource(formData: FormData, active: () => boolean): Promise<boolean> {
    const fail = (message: string): false => {
      if (active()) this.urlError = message;
      return false;
    };
    formData.set('importMode', this.importMode);
    if (this.importMode === 'file' || (this.mode === 'configure' && !this.specificationUrl.trim())) return true;
    const parsed = importOpenApiCatalogUrlRequestSchema.safeParse({ url: this.specificationUrl });
    if (!parsed.success) {
      return fail('Enter a valid HTTPS URL without embedded credentials.');
    }
    let response: Response;
    try {
      response = await this.request(parsed.data.url, { method: 'GET', credentials: 'omit', redirect: 'follow' });
    } catch {
      return fail('The OpenAPI document could not be retrieved from that URL.');
    }
    if (!response.ok) return fail('The OpenAPI document could not be retrieved from that URL.');
    let document: unknown;
    try {
      document = await response.json();
    } catch {
      return fail('The retrieved OpenAPI document is not valid JSON.');
    }
    if (typeof document !== 'object' || document === null || Array.isArray(document)) {
      return fail('The retrieved OpenAPI document must be a JSON object.');
    }
    const serialized = JSON.stringify(document);
    if (this.mode === 'create' && new Blob([serialized]).size > OPEN_API_CATALOG_FILE_MAX_BYTES) return fail('The JSON document must be 10 MiB or smaller.');
    if (!active()) return false;
    formData.set('document', serialized);
    formData.delete('file');
    return true;
  };

  beginSubmit = (): void => {
    this.submitting = true;
    this.message = '';
  };

  completeSubmit = (result: unknown): void => {
    this.submitting = false;
    if (typeof result === 'object' && result !== null && 'type' in result && result.type === 'redirect') {
      this.close();
      this.toast?.success(this.mode === 'create' ? 'OpenAPI connector added.' : 'OpenAPI connector configuration saved.');
      return;
    }
    if (typeof result !== 'object' || result === null || !('data' in result)) return;
    const data = result.data;
    if (typeof data !== 'object' || data === null) return;
    const status = 'status' in data && typeof data.status === 'string' ? data.status : '';
    const message = 'message' in data && typeof data.message === 'string' ? data.message : '';
    if (status === 'invalid' || status === 'conflict') {
      this.message = message;
      return;
    }
    if (status === 'warning') {
      this.setupBlocked = true;
      this.message = message;
      this.toast?.warning(message || 'The operation completed with a warning.');
      return;
    }
    if (status === 'failed' || status === 'network') {
      this.toast?.error(message || 'The operation could not be completed. Try again.');
      return;
    }
    if (status === 'saved' || status === 'success') this.toast?.success(message || 'OpenAPI connector saved.');
  };

  private show(trigger: HTMLElement): void {
    this.returnFocus = trigger;
    this.open = true;
    if (this.mode === 'configure' && typeof document !== 'undefined') {
      queueMicrotask(() => document.getElementById('openapi-setup-display-name')?.focus());
    }
  }
}
