import {
  importOpenApiCatalogUrlRequestSchema,
  normalizeToolNamePrefix,
  openApiConfigurationResponseSchema
} from '$lib/admin/openapi-connectors';
import type { ToastApi } from '$lib/components/feedback';

export type OpenApiSetupMode = 'create' | 'configure';
export type OpenApiAuthenticationType = 'none' | 'bearer';
export type OpenApiImportMode = 'file' | 'url';

export class OpenApiConnectorSetupState {
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
  private returnFocus: HTMLElement | null = null;
  private toolNamePrefixEdited = false;

  constructor(
    private readonly request: typeof globalThis.fetch = globalThis.fetch,
    private readonly toast?: ToastApi
  ) {}

  showCreate = (trigger: HTMLElement): void => {
    this.mode = 'create';
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
    let response: Response;
    try {
      response = await this.request(`/admin/openapi-connectors/${encodeURIComponent(connectorId)}/configuration`);
    } catch {
      this.toast?.error('Bearer configuration could not be loaded. Try again.');
      return;
    }
    if (!response.ok) {
      this.toast?.error('Bearer configuration could not be loaded. Try again.');
      return;
    }
    const configuration = openApiConfigurationResponseSchema.parse(await response.json());
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
    if (event.key === 'Tab') {
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
    this.displayName = event.currentTarget.value;
    if (!this.toolNamePrefixEdited) this.toolNamePrefix = normalizeToolNamePrefix(this.displayName);
  };

  setToolNamePrefix = (event: Event): void => {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    this.toolNamePrefix = event.currentTarget.value;
    this.toolNamePrefixEdited = true;
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

  prepareSubmission = async (formData: FormData): Promise<boolean> => {
    formData.set('importMode', this.importMode);
    if (this.importMode === 'file' || (this.mode === 'configure' && !this.specificationUrl.trim())) return true;
    const parsed = importOpenApiCatalogUrlRequestSchema.safeParse({ url: this.specificationUrl });
    if (!parsed.success) {
      this.urlError = 'Enter a valid HTTPS URL without embedded credentials.';
      return false;
    }
    let response: Response;
    try {
      response = await this.request(parsed.data.url, { method: 'GET', credentials: 'omit', redirect: 'follow' });
    } catch {
      this.urlError = 'The OpenAPI document could not be retrieved from that URL.';
      return false;
    }
    if (!response.ok) {
      this.urlError = 'The OpenAPI document could not be retrieved from that URL.';
      return false;
    }
    let document: unknown;
    try {
      document = await response.json();
    } catch {
      this.urlError = 'The retrieved OpenAPI document is not valid JSON.';
      return false;
    }
    if (typeof document !== 'object' || document === null || Array.isArray(document)) {
      this.urlError = 'The retrieved OpenAPI document must be a JSON object.';
      return false;
    }
    formData.set('document', JSON.stringify(document));
    formData.delete('file');
    return true;
  };

  beginSubmit = (): void => {
    this.submitting = true;
    this.message = '';
  };

  completeSubmit = (result: unknown): void => {
    this.submitting = false;
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
    if (typeof document !== 'undefined') {
      queueMicrotask(() => document.getElementById('openapi-setup-display-name')?.focus());
    }
  }
}
