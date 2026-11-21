import { tick } from 'svelte';
import { PersonalOAuthSetupState } from '../personal-mcp-servers/personal-oauth-setup-state.svelte';
import type { McpSetupDraft, McpSetupMode } from './mcp-endpoint-setup-state.svelte';
import { AdminApi, adminApi } from '#lib/admin/infrastructure/admin-api.js';
import { BrowserRequestError } from '#lib/admin/infrastructure/browser-request.js';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import { browserTransport } from '#lib/admin/infrastructure/transport.js';
import { mapResourceCatalog, type PromptCatalog, type ResourceCatalog } from '#lib/admin/capability-catalogs.js';
import { type DownstreamMcpConnector, type DownstreamMcpConnectorSummary, type DownstreamMcpToolList } from '#lib/admin/downstream-mcp-connectors.js';
import { type InvocationPolicyTool } from '#lib/admin/invocation-policy.js';
import { SelectionDetailController } from '#lib/components/admin/shared/selection-detail-controller.svelte.js';
import { InMemorySelectionUrlAdapter, type SelectionUrlPort } from '#lib/components/admin/shared/selection-url-port.js';

export type DownstreamMcpWorkspaceBundle = {
  mode: 'personal';
  connector: DownstreamMcpConnector;
  catalog?: never;
  promptCatalog?: never;
  resourceCatalog?: never;
  invocationPolicies?: never;
} | {
  mode: 'shared';
  connector: DownstreamMcpConnector;
  catalog: DownstreamMcpToolList;
  promptCatalog: PromptCatalog;
  resourceCatalog: ResourceCatalog;
  invocationPolicies?: InvocationPolicyTool[];
};

export type DownstreamMcpModal = 'choose' | 'personal' | 'personal-edit' | 'personal-setup' | 'create' | 'configure' | 'delete' | null;

export interface DownstreamMcpCreateValues {
  displayName: string;
  toolNamePrefix: string;
  capabilityDescription: string;
  endpointUrl: string;
  publicPath: string;
  authMode: string;
  headerType?: string;
  customHeaderName?: string;
}

export interface DownstreamMcpWorkspaceForm {
  message?: string;
  status?: string;
  mode?: string;
  values?: DownstreamMcpCreateValues;
}

type DownstreamBundleLoader = (connectorId: string, signal?: AbortSignal) => Promise<DownstreamMcpWorkspaceBundle>;

import { DownstreamMcpMutationState } from './downstream-mcp-mutation-state.svelte';
import { suggestedConnectorId, suggestedToolNamePrefix } from '../shared/connector-name-suggestions';

export class DownstreamMcpWorkspaceState {
  modal = $state<DownstreamMcpModal>(null);
  authMode = $state<'none' | 'static_bearer'>('none');
  headerType = $state<'bearer' | 'basic' | 'custom'>('bearer');
  customHeaderName = $state('');
  submitting = $state(false);
  submitError = $state<string | null>(null);
  menuOpen = $state(false);
  returnFocus = $state<HTMLElement | null>(null);
  createPublicPath = $state('');
  toolNamePrefix = $state('connector');
  publicPathEdited = $state(false);
  toolNamePrefixEdited = $state(false);
  capabilityDescriptionConnectorId = $state<string | null>(null);
  readonly personalSetup: PersonalOAuthSetupState;
  #createDraft = $state.raw<McpSetupDraft>();
  #previousForm = $state.raw<DownstreamMcpWorkspaceForm>();
  private publicationFromCheck = false;

  get createDraft(): Readonly<McpSetupDraft> | undefined { return this.#createDraft; }

  currentForm = (form?: DownstreamMcpWorkspaceForm): DownstreamMcpWorkspaceForm | undefined =>
    form === this.#previousForm ? undefined : form;
  private readonly selection: SelectionDetailController<{ connector_id: string }, DownstreamMcpWorkspaceBundle>;

  get bundle(): DownstreamMcpWorkspaceBundle | null { return this.operations.authenticationLost || this.operations.blocked ? null : this.selection.detail; }
  get detailLoading(): boolean { return this.selection.loading; }
  get detailFailed(): boolean { return this.selection.failed; }
  get selectedConnectorId(): string | null { return this.selection.selectedId; }

  constructor(failedMode?: string, values?: DownstreamMcpCreateValues, initialBundle?: DownstreamMcpWorkspaceBundle, bundleLoader: DownstreamBundleLoader = loadDownstreamBundle, initialConnectorId?: string, initialDetailFailed?: boolean, connectors: { connector_id: string }[] = initialBundle ? [initialBundle.connector] : [], selectionUrl: SelectionUrlPort = new InMemorySelectionUrlAdapter(), readonly operations: DownstreamMcpMutationState = new DownstreamMcpMutationState()) {
    const api = adminApi();
    this.personalSetup = new PersonalOAuthSetupState(api.personalOAuthSetup, api.personalServers, this.operations.setPersonalValidation, this.operations.reconcilePublication, this.operations.loseAccess, this.operations.setSetupLocked, () => !this.operations.locked);
    this.selection = new SelectionDetailController({
      items: connectors,
      itemId: (connector) => connector.connector_id,
      selectedId: initialBundle?.connector.connector_id ?? initialConnectorId,
      initialDetail: initialBundle,
      initialDetailFailed,
      loadDetail: async (id, signal) => {
        try { return await bundleLoader(id, signal); }
        catch (error) {
          if (error instanceof AuthenticationRequiredError || error instanceof HttpError && [401, 403].includes(error.status)) this.operations.loseAccess();
          throw error instanceof BrowserRequestError ? error : new BrowserRequestError(error instanceof HttpError ? error.status : undefined, error);
        }
      },
      allowUnknownSelection: false,
      url: selectionUrl,
      onSelectionChange: () => {
        this.publicationFromCheck = false;
        this.personalSetup.detach();
        this.capabilityDescriptionConnectorId = null;
        this.menuOpen = false;
        this.modal = null;
        this.operations.cancel();
      }
    });
    if (failedMode !== 'create' || !values) return;
    this.modal = 'create';
    this.createPublicPath = publicPathSlug(values.publicPath);
    this.toolNamePrefix = values.toolNamePrefix;
    this.publicPathEdited = true;
    this.toolNamePrefixEdited = true;
    this.setAuthMode(values.authMode);
    this.setHeaderType(values.headerType ?? 'bearer');
    this.customHeaderName = values.customHeaderName ?? '';
  }

  beginCreate = (trigger: HTMLElement, previousForm?: DownstreamMcpWorkspaceForm): void => {
    if (this.operations.locked) return;
    this.#previousForm = previousForm;
    this.#createDraft = undefined;
    this.open('choose', trigger);
  };

  completeSharedSetup = (mode: Exclude<McpSetupMode, 'personal'>, draft: McpSetupDraft): void => {
    const trigger = this.returnFocus;
    if (this.modal !== 'choose' || !trigger || this.operations.locked) return;
    this.open('create', trigger);
    this.#createDraft = { ...draft };
    this.setAuthMode(mode);
    this.suggestCreateIdentifiers(draft.displayName);
  };

  returnToAccess = (): void => {
    if (this.operations.locked || this.submitting || (this.modal !== 'personal' && (this.modal !== 'create' || !this.#createDraft))) return;
    this.submitError = null;
    this.modal = 'choose';
  };

  open = (modal: Exclude<DownstreamMcpModal, null>, trigger: HTMLElement, connector?: DownstreamMcpConnector): void => {
    if (this.operations.locked) return;
    if (modal === 'configure' && connector && connector.authorization_mode !== 'shared') return;
    if ((modal === 'personal-edit' || modal === 'personal-setup') && (!connector || connector.authorization_mode !== 'personal')) return;
    const menuTrigger = typeof trigger.closest === 'function' ? trigger.closest('[role="menu"]')?.parentElement?.querySelector<HTMLElement>('button[aria-haspopup="menu"]') : null;
    this.returnFocus = this.modal === 'personal-setup' && this.returnFocus ? this.returnFocus : menuTrigger ?? trigger;
    this.menuOpen = false;
    this.authMode = connector?.auth_mode === 'static_bearer' ? 'static_bearer' : 'none';
    this.headerType = connector?.header_type ?? 'bearer';
    this.customHeaderName = connector?.custom_header_name ?? '';
    if (modal === 'create') {
      this.createPublicPath = '';
      this.toolNamePrefix = 'connector';
      this.publicPathEdited = false;
      this.toolNamePrefixEdited = false;
    } else if (connector) {
      this.toolNamePrefix = connector.tool_name_prefix;
      this.toolNamePrefixEdited = true;
    }
    this.modal = modal;
  };

  close = (): void => {
    this.modal = null;
    this.submitting = false;
    this.submitError = null;
    const trigger = this.returnFocus;
    trigger?.focus();
    void tick().then(() => { if (this.modal === null && trigger?.isConnected) trigger.focus(); });
  };

  openCapabilityDescription = (connectorId: string, trigger: HTMLElement): void => {
    if (this.operations.locked) return;
    this.menuOpen = false;
    this.modal = null;
    this.returnFocus = trigger;
    this.capabilityDescriptionConnectorId = connectorId;
  };

  closeCapabilityDescription = (): void => {
    this.capabilityDescriptionConnectorId = null;
    this.returnFocus?.focus();
  };

  checkConfiguration = (trigger: HTMLElement, connector: DownstreamMcpConnector | undefined): void => {
    if (!connector || this.operations.locked || connector.authorization_mode !== 'personal' || this.selectedConnectorId !== connector.connector_id) return;
    this.open('personal-setup', trigger, connector);
    void this.personalSetup.check();
  };

  publishChecked = (connector: DownstreamMcpConnectorSummary): void => {
    if (this.modal !== 'personal-setup' || this.selectedConnectorId !== connector.connector_id || connector.publication_status === 'published' || !this.personalSetup.validated || this.operations.locked || !this.operations.canPublish(connector)) return;
    this.close();
    this.requestPublication(connector);
    this.publicationFromCheck = true;
  };

  cancelPublication = (): void => {
    if (this.operations.busy) return;
    this.operations.cancel();
    this.finishCheckedPublication();
  };

  confirmPublication = async (): Promise<void> => {
    await this.operations.confirm();
    if (!this.operations.pending) this.finishCheckedPublication();
  };

  private finishCheckedPublication(): void {
    if (!this.publicationFromCheck) return;
    this.publicationFromCheck = false;
    if (!this.operations.locked && this.modal === null) this.close();
  }

  requestPublication = (connector: DownstreamMcpConnectorSummary): void => {
    if (this.operations.locked || connector.publication_status !== 'published' && !this.operations.canPublish(connector)) return;
    this.operations.request(connector.publication_status === 'published' ? 'unpublish' : 'publish', connector.connector_id, connector.display_name);
    this.menuOpen = false;
  };

  selectConnector = (connectorId: string): void => {
    if (this.operations.locked) return;
    this.selection.select(connectorId);
  };

  retrySelected = (): void => {
    this.selection.retry();
  };

  reconcileTools = (connectorId: string, tools: DownstreamMcpToolList['tools']): void => {
    this.selection.updateDetail(connectorId, (cached) => cached.mode === 'shared' ? { ...cached, catalog: { ...cached.catalog, tools } } : cached);
  };

  reconcilePrompts = (connectorId: string, promptCatalog: PromptCatalog): void => {
    this.selection.updateDetail(connectorId, (cached) => cached.mode === 'shared' ? { ...cached, promptCatalog } : cached);
  };

  reconcileResources = (connectorId: string, resourceCatalog: ResourceCatalog): void => {
    this.selection.updateDetail(connectorId, (cached) => cached.mode === 'shared' ? { ...cached, resourceCatalog } : cached);
  };

  setAuthMode = (value: string): void => {
    this.authMode = value === 'static_bearer' ? value : 'none';
  };

  setHeaderType = (value: string): void => {
    this.headerType = value === 'basic' || value === 'custom' ? value : 'bearer';
  };

  updateCustomHeaderName = (event: Event): void => {
    if (!event.currentTarget || !('value' in event.currentTarget)) return;
    this.customHeaderName = String(event.currentTarget.value);
  };

  updateDisplayName = (event: Event): void => {
    if (!event.currentTarget || !('value' in event.currentTarget)) return;
    this.suggestCreateIdentifiers(String(event.currentTarget.value));
  };

  private suggestCreateIdentifiers(displayName: string): void {
    const suggestion = suggestedConnectorId(displayName).slice(0, 63);
    if (!this.publicPathEdited) this.createPublicPath = suggestion;
    if (!this.toolNamePrefixEdited) this.toolNamePrefix = suggestedToolNamePrefix(displayName);
  }

  updateToolNamePrefix = (event: Event): void => {
    if (!event.currentTarget || !('value' in event.currentTarget)) return;
    this.toolNamePrefixEdited = true;
    this.toolNamePrefix = String(event.currentTarget.value);
  };

  updatePublicPath = (event: Event): void => {
    if (!event.currentTarget || !('value' in event.currentTarget)) return;
    this.publicPathEdited = true;
    this.createPublicPath = String(event.currentTarget.value);
  };

  beginSubmit = (): void => { this.submitError = null; this.submitting = true; };
  finishSubmit = (): void => { this.submitting = false; };
  failSubmit = (message: string): void => { this.submitError = message; this.submitting = false; };
  setMenuOpen = (open: boolean): void => { this.menuOpen = open; };
  handleKeydown = (event: KeyboardEvent): void => { if (event.key === 'Escape' && this.modal !== 'choose' && this.modal !== 'personal-edit' && this.modal !== 'personal-setup') this.close(); };
}

async function loadDownstreamBundle(connectorId: string, signal?: AbortSignal): Promise<DownstreamMcpWorkspaceBundle> {
  const transport = browserTransport();
  const api = new AdminApi({ request: (options) => transport.request({ ...options, signal }) }).downstreamMcpConnectors;
  const definition = await api.get(connectorId);
  if (definition.authorization_mode === 'personal') return { mode: 'personal', connector: definition };
  const [connector, catalog, promptCatalog, resources, activation] = await Promise.all([
    Promise.resolve(definition), api.tools(connectorId), api.prompts(connectorId), api.resources(connectorId), api.listActivations(connectorId)
  ]);
  return { mode: 'shared', connector, catalog, promptCatalog, resourceCatalog: mapResourceCatalog(resources), invocationPolicies: activation.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) };
}

export function publicPathSlug(publicPath: string): string {
  return publicPath.startsWith('/mcp/proxies/') ? publicPath.slice('/mcp/proxies/'.length) : publicPath.replace(/^\/+/, '');
}
