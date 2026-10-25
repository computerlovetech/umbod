import type { PersonalServerAvailability } from '$lib/admin/personal-mcp-servers/domain/availability';
import { AdminApi } from '$lib/admin/infrastructure/admin-api';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import { browserTransport } from '$lib/admin/infrastructure/transport';
import { mapResourceCatalog, type PromptCatalog, type ResourceCatalog } from '$lib/admin/capability-catalogs';
import { type DownstreamMcpConnector, type DownstreamMcpToolList } from '$lib/admin/downstream-mcp-connectors';
import { type InvocationPolicyTool } from '$lib/admin/invocation-policy';
import { SelectionDetailController } from '$lib/components/admin/shared/selection-detail-controller.svelte';
import { InMemorySelectionUrlAdapter, type SelectionUrlPort } from '$lib/components/admin/shared/selection-url-port';

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

export type DownstreamMcpModal = 'choose' | 'personal' | 'create' | 'configure' | 'delete' | null;
export type DownstreamMcpPublicationActionLabel = 'Publish' | 'Unpublish';
export type DownstreamMcpPendingPublication = {
  form: HTMLFormElement;
  connectorName: string;
  actionLabel: DownstreamMcpPublicationActionLabel;
};

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

type DownstreamBundleLoader = (connectorId: string, signal?: AbortSignal) => Promise<DownstreamMcpWorkspaceBundle>;

import { DownstreamMcpMutationState } from './downstream-mcp-mutation-state.svelte';
import { suggestedConnectorId, suggestedToolNamePrefix } from '../shared/connector-name-suggestions';

export class DownstreamMcpWorkspaceState {
  readonly operations = new DownstreamMcpMutationState();
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
  pendingPublication = $state<DownstreamMcpPendingPublication | null>(null);
  private readonly selection: SelectionDetailController<{ connector_id: string }, DownstreamMcpWorkspaceBundle>;

  get bundle(): DownstreamMcpWorkspaceBundle | null { return this.operations.authenticationLost || this.operations.blocked ? null : this.selection.detail; }
  get detailLoading(): boolean { return this.selection.loading; }
  get detailFailed(): boolean { return this.selection.failed; }
  get selectedConnectorId(): string | null { return this.selection.selectedId; }

  constructor(failedMode?: string, values?: DownstreamMcpCreateValues, initialBundle?: DownstreamMcpWorkspaceBundle, bundleLoader: DownstreamBundleLoader = loadDownstreamBundle, initialConnectorId?: string, initialDetailFailed?: boolean, connectors: { connector_id: string }[] = initialBundle ? [initialBundle.connector] : [], selectionUrl: SelectionUrlPort = new InMemorySelectionUrlAdapter()) {
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
        this.capabilityDescriptionConnectorId = null;
        this.menuOpen = false;
        this.modal = null;
        this.pendingPublication = null;
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

  beginCreate = (availability: PersonalServerAvailability, trigger: HTMLElement): void => {
    this.open(availability.registration === 'enabled' ? 'choose' : 'create', trigger);
  };

  open = (modal: Exclude<DownstreamMcpModal, null>, trigger: HTMLElement, connector?: DownstreamMcpConnector): void => {
    if (this.operations.locked) return;
    if (modal === 'configure' && connector && connector.authorization_mode !== 'shared') return;
    this.returnFocus = trigger;
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
    this.returnFocus?.focus();
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

  requestPublicationConfirmation = (form: HTMLFormElement, connectorName: string, actionLabel: DownstreamMcpPublicationActionLabel): void => {
    if (this.operations.locked) return;
    this.pendingPublication = { form, connectorName, actionLabel };
  };

  cancelPublication = (): void => {
    this.pendingPublication = null;
    this.menuOpen = false;
  };

  confirmPublication = (): void => {
    if (this.operations.locked) return;
    const form = this.pendingPublication?.form;
    form?.requestSubmit();
    this.pendingPublication = null;
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
    const displayName = String(event.currentTarget.value);
    const suggestion = suggestedConnectorId(displayName).slice(0, 63);
    if (!this.publicPathEdited) this.createPublicPath = suggestion;
    if (!this.toolNamePrefixEdited) this.toolNamePrefix = suggestedToolNamePrefix(displayName);
  };

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
  handleKeydown = (event: KeyboardEvent): void => { if (event.key === 'Escape') this.close(); };
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
