import { emptyPromptCatalog, emptyResourceCatalog, resourceActivationKey, type CapabilityActivationStatus, type PromptCatalog, type ResourceCatalog } from '$lib/admin/capability-catalogs';
import type { ConnectorListItem, ConnectorToolActivationStatus } from '$lib/admin/connectors';
import type { ConnectorDetailBundle } from '$lib/admin/connector-details-browser-api';
import { SelectionDetailController } from '$lib/components/admin/shared/selection-detail-controller.svelte';
import { InMemorySelectionUrlAdapter, type SelectionUrlPort } from '$lib/components/admin/shared/selection-url-port';
import type { InvocationPolicyMode, InvocationPolicyTool } from '$lib/admin/invocation-policy';

export type ConnectorToolActivationDraft = {
  operationName: string;
  activationStatus: ConnectorToolActivationStatus;
};

export type ConnectorPromptActivationDraft = {
  promptId: string;
  activationStatus: CapabilityActivationStatus;
};

export type ConnectorResourceActivationDraft = {
  resourceId: string;
  kind: 'resource' | 'resource_template';
  activationStatus: CapabilityActivationStatus;
};

type PublicationActionLabel = 'Publish' | 'Unpublish';

type PendingPublication = {
  form: HTMLFormElement;
  connectorName: string;
  actionLabel: PublicationActionLabel;
};

type ConnectorDetailLoader = (connectorId: string, signal?: AbortSignal) => Promise<ConnectorDetailBundle>;

type ConnectorListStateOptions = {
  selectedConnectorId?: string | null;
  initialDetail?: ConnectorDetailBundle;
  initialDetailFailed?: boolean;
  loadDetail?: ConnectorDetailLoader;
  selectionUrl?: SelectionUrlPort;
};

export class ConnectorListState {
  connectors = $state.raw<ConnectorListItem[]>([]);

  pendingPublication = $state<PendingPublication | null>(null);
  visibleAction = $state<'configuration' | null>(null);
  openMenuConnectorId = $state<string | null>(null);
  capabilityDescriptionConnectorId = $state<string | null>(null);
  toolActivationDrafts = $state.raw<Record<string, ConnectorToolActivationStatus>>({});
  promptActivationDrafts = $state.raw<Record<string, CapabilityActivationStatus>>({});
  resourceActivationDrafts = $state.raw<Record<string, CapabilityActivationStatus>>({});
  policies = $state.raw<Record<string, InvocationPolicyTool>>({});
  persistedPolicies = $state.raw<Record<string, InvocationPolicyTool>>({});
  policyConflicts = $state.raw<Record<string, boolean>>({});
  private readonly selection: SelectionDetailController<ConnectorListItem, ConnectorDetailBundle>;

  get selectedConnectorId(): string | null { return this.selection.selectedId; }
  get detailLoading(): boolean { return this.selection.loading; }
  get detailFailed(): boolean { return this.selection.failed; }
  get selectedPromptCatalog(): PromptCatalog { return this.selection.detail?.promptCatalog ?? emptyPromptCatalog(); }
  get selectedResourceCatalog(): ResourceCatalog { return this.selection.detail?.resourceCatalog ?? emptyResourceCatalog(); }

  selectedConnector = $derived.by((): ConnectorListItem => {
    const selectedConnector = this.selection.selectedItem as ConnectorListItem;
    const mounted = this.selection.detail;
    return selectedConnector && mounted && selectedConnector.id === this.selection.selectedId
      ? { ...selectedConnector, tools: mounted.detail.tools, configurationFields: mounted.configurationFields }
      : selectedConnector;
  });

  selectedToolActivationDrafts = $derived.by((): ConnectorToolActivationDraft[] => {
    return (
      this.selectedConnector?.tools.map((tool) => ({
        operationName: tool.operationName,
        activationStatus: this.toolActivationDrafts[tool.operationName] ?? tool.activationStatus
      })) ?? []
    );
  });

  selectedToolActivationDraftsJson = $derived(JSON.stringify(this.selectedToolActivationDrafts));

  selectedPromptActivationDrafts = $derived.by((): ConnectorPromptActivationDraft[] => {
    return this.selectedPromptCatalog.prompts
      .map((prompt) => ({
        promptId: prompt.name,
        activationStatus: this.promptActivationDrafts[prompt.name] ?? prompt.activation_status
      }))
      .filter((draft) => {
        const prompt = this.selectedPromptCatalog.prompts.find((candidate) => candidate.name === draft.promptId);
        return prompt !== undefined && draft.activationStatus !== prompt.activation_status;
      });
  });

  selectedPromptActivationDraftsJson = $derived(JSON.stringify(this.selectedPromptActivationDrafts));

  selectedResourceActivationDrafts = $derived.by((): ConnectorResourceActivationDraft[] => {
    return this.selectedResourceCatalog.resources
      .map((resource) => {
        const resourceId = resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
        const key = resourceActivationKey(resource.kind, resourceId);
        return {
          resourceId,
          kind: resource.kind,
          activationStatus: this.resourceActivationDrafts[key] ?? resource.activationStatus
        };
      })
      .filter((draft) => {
        const resource = this.selectedResourceCatalog.resources.find((candidate) =>
          candidate.kind === draft.kind &&
          (candidate.kind === 'resource' ? candidate.uri : candidate.uriTemplate) === draft.resourceId
        );
        return resource !== undefined && draft.activationStatus !== resource.activationStatus;
      });
  });

  selectedResourceActivationDraftsJson = $derived(JSON.stringify(this.selectedResourceActivationDrafts));

  hasUnsavedToolChanges = $derived.by(() => {
    return (this.selectedConnector?.tools.some((tool) => this.draftToolActivationStatus(tool.operationName) !== tool.activationStatus) ?? false) || this.changedPolicies.length > 0;
  });

  hasUnsavedPromptChanges = $derived(this.selectedPromptActivationDrafts.length > 0);
  hasUnsavedResourceChanges = $derived(this.selectedResourceActivationDrafts.length > 0);

  modalTitle = $derived(
    this.pendingPublication ? `${this.pendingPublication.actionLabel} ${this.pendingPublication.connectorName}?` : ''
  );

  modalMessage = $derived(
    this.pendingPublication
      ? `Please confirm that you want to ${this.pendingPublication.actionLabel.toLowerCase()} the built-in connector ${this.pendingPublication.connectorName}.`
      : ''
  );

  constructor(connectors: ConnectorListItem[], options: ConnectorListStateOptions = {}) {
    this.connectors = connectors;
    this.selection = new SelectionDetailController({
      items: connectors,
      itemId: (connector) => connector.id,
      selectedId: options.selectedConnectorId,
      initialDetail: options.initialDetail,
      initialDetailFailed: options.initialDetailFailed,
      loadDetail: options.loadDetail
        ? async (connectorId, signal) => {
            const bundle = await options.loadDetail!(connectorId, signal);
            this.mountDetail(connectorId, bundle);
            if (this.selectedConnectorId === connectorId) this.replacePolicies(bundle.invocationPolicies ?? []);
            return bundle;
          }
        : undefined,
      url: options.selectionUrl ?? new InMemorySelectionUrlAdapter(),
      onSelectionChange: () => {
        this.visibleAction = null;
        this.capabilityDescriptionConnectorId = null;
        this.resetToolActivationDrafts();
        this.resetPromptActivationDrafts();
        this.resetResourceActivationDrafts();
        this.replacePolicies([]);
      }
    });
    if (options.initialDetail && this.selectedConnectorId) {
      this.mountDetail(this.selectedConnectorId, options.initialDetail);
      this.reconcilePolicies(options.initialDetail.invocationPolicies ?? []);
    }
  }

  selectConnector = (connectorId: string): void => {
    this.selection.select(connectorId);
    const cached = this.selection.readDetail(connectorId);
    if (cached) {
      this.mountDetail(connectorId, cached);
      this.replacePolicies(cached.invocationPolicies ?? []);
    }
  };

  retryDetail = (): void => {
    this.selection.retry();
  };

  private mountDetail = (connectorId: string, bundle: ConnectorDetailBundle): void => {
    this.connectors = this.connectors.map((connector) => connector.id === connectorId
      ? { ...connector, tools: bundle.detail.tools, configurationFields: bundle.configurationFields }
      : connector);
  };

  setMenuOpen = (connectorId: string, open: boolean): void => {
    this.openMenuConnectorId = open ? connectorId : null;
    if (open) this.selectConnector(connectorId);
  };

  showConfiguration = (connectorId: string): void => {
    this.selectConnector(connectorId);
    this.openMenuConnectorId = null;
    this.visibleAction = 'configuration';
    this.resetToolActivationDrafts();
  };

  showCapabilityDescription = (connectorId: string): void => {
    this.selectConnector(connectorId);
    this.openMenuConnectorId = null;
    this.capabilityDescriptionConnectorId = connectorId;
  };

  closeCapabilityDescription = (): void => {
    this.capabilityDescriptionConnectorId = null;
  };

  closeMenu = (): void => {
    this.openMenuConnectorId = null;
  };

  toggleConfiguration = (): void => {
    this.visibleAction = this.visibleAction === 'configuration' ? null : 'configuration';
    this.resetToolActivationDrafts();
  };

  draftToolActivationStatus = (operationName: string): ConnectorToolActivationStatus => {
    const tool = this.selectedConnector?.tools.find((candidate) => candidate.operationName === operationName);
    return this.toolActivationDrafts[operationName] ?? tool?.activationStatus ?? 'disabled';
  };

  toolActivationIsEnabled = (operationName: string): boolean => {
    return this.draftToolActivationStatus(operationName) === 'enabled';
  };

  draftPromptActivationStatus = (promptId: string): CapabilityActivationStatus => {
    const prompt = this.selectedPromptCatalog.prompts.find((candidate) => candidate.name === promptId);
    return this.promptActivationDrafts[promptId] ?? prompt?.activation_status ?? 'disabled';
  };

  promptActivationIsEnabled = (promptId: string): boolean => {
    return this.draftPromptActivationStatus(promptId) === 'enabled';
  };

  draftResourceActivationStatus = (
    resourceId: string,
    kind: 'resource' | 'resource_template'
  ): CapabilityActivationStatus => {
    const key = resourceActivationKey(kind, resourceId);
    const resource = this.selectedResourceCatalog.resources.find((candidate) =>
      candidate.kind === kind &&
      (candidate.kind === 'resource' ? candidate.uri : candidate.uriTemplate) === resourceId
    );
    return this.resourceActivationDrafts[key] ?? resource?.activationStatus ?? 'disabled';
  };

  resourceActivationIsEnabled = (resourceId: string, kind: 'resource' | 'resource_template'): boolean => {
    return this.draftResourceActivationStatus(resourceId, kind) === 'enabled';
  };

  policyMode = (toolId: string): InvocationPolicyMode => this.policies[toolId]?.mode ?? 'direct';
  setPolicy = (toolId: string, mode: InvocationPolicyMode): void => {
    if (this.policies[toolId]) this.policies = { ...this.policies, [toolId]: { ...this.policies[toolId], mode } };
  };
  changedPolicies = $derived.by(() => Object.values(this.policies).filter((policy) => this.persistedPolicies[policy.tool_id]?.mode !== policy.mode).map((policy) => ({ tool_id: policy.tool_id, mode: policy.mode, expected_revision: this.persistedPolicies[policy.tool_id].revision })));
  invocationPoliciesJson = $derived.by(() => JSON.stringify({ tools: this.changedPolicies }));
  reconcilePolicies = (policies: InvocationPolicyTool[], conflict = false): void => {
    const incoming = Object.fromEntries(policies.map((policy) => [policy.tool_id, policy]));
    this.persistedPolicies = { ...this.persistedPolicies, ...incoming };
    if (!conflict) this.policies = { ...this.policies, ...incoming };
    this.policyConflicts = conflict ? Object.fromEntries(policies.map((policy) => [policy.tool_id, true])) : {};
    if (this.selectedConnectorId) this.cachePolicies(this.selectedConnectorId, Object.values(this.persistedPolicies));
  };

  reconcileAuthoritativePolicies = (policies: InvocationPolicyTool[]): void => {
    const incoming = Object.fromEntries(policies.map((policy) => [policy.tool_id, policy]));
    const drafts = Object.fromEntries(Object.values(this.policies)
      .filter((policy) => incoming[policy.tool_id] && incoming[policy.tool_id].mode !== policy.mode)
      .map((policy) => [policy.tool_id, { ...incoming[policy.tool_id], mode: policy.mode }]));
    this.persistedPolicies = incoming;
    this.policies = { ...incoming, ...drafts };
    if (this.selectedConnectorId) this.cachePolicies(this.selectedConnectorId, policies);
  };

  private cachePolicies = (connectorId: string, policies: InvocationPolicyTool[]): void => {
    this.selection.updateDetail(connectorId, (cached) => ({ ...cached, invocationPolicies: policies }));
  };

  replacePolicies = (policies: InvocationPolicyTool[]): void => {
    const incoming = Object.fromEntries(policies.map((policy) => [policy.tool_id, policy]));
    this.persistedPolicies = incoming;
    this.policies = incoming;
    this.policyConflicts = {};
  };

  setToolActivation = (operationName: string, enabled: boolean): void => {
    this.toolActivationDrafts = {
      ...this.toolActivationDrafts,
      [operationName]: enabled ? 'enabled' : 'disabled'
    };
  };

  setPromptActivation = (promptId: string, enabled: boolean): void => {
    this.promptActivationDrafts = {
      ...this.promptActivationDrafts,
      [promptId]: enabled ? 'enabled' : 'disabled'
    };
  };

  setResourceActivation = (
    resourceId: string,
    kind: 'resource' | 'resource_template',
    enabled: boolean
  ): void => {
    this.resourceActivationDrafts = {
      ...this.resourceActivationDrafts,
      [resourceActivationKey(kind, resourceId)]: enabled ? 'enabled' : 'disabled'
    };
  };

  resetToolActivationDrafts = (): void => {
    this.toolActivationDrafts = {};
  };

  resetPromptActivationDrafts = (): void => {
    this.promptActivationDrafts = {};
  };

  resetResourceActivationDrafts = (): void => {
    this.resourceActivationDrafts = {};
  };

  captureToolActivationSubmission = (): { connectorId: string; changes: Record<string, ConnectorToolActivationStatus> } | null => {
    return this.selectedConnectorId ? { connectorId: this.selectedConnectorId, changes: { ...this.toolActivationDrafts } } : null;
  };

  capturePromptActivationSubmission = (): { connectorId: string; changes: Record<string, CapabilityActivationStatus> } | null => {
    return this.selectedConnectorId ? { connectorId: this.selectedConnectorId, changes: { ...this.promptActivationDrafts } } : null;
  };

  captureResourceActivationSubmission = (): { connectorId: string; changes: Record<string, CapabilityActivationStatus> } | null => {
    return this.selectedConnectorId ? { connectorId: this.selectedConnectorId, changes: { ...this.resourceActivationDrafts } } : null;
  };

  reconcileAuthoritativeActivations = (connectorId: string, tools: Array<{ tool_id: string; activation_status: ConnectorToolActivationStatus }>): void => {
    const authoritative = Object.fromEntries(tools.map((tool) => [tool.tool_id, tool.activation_status]));
    const drafts = { ...this.toolActivationDrafts };
    this.markToolActivationsSaved(connectorId, authoritative);
    if (this.selectedConnectorId === connectorId) {
      this.toolActivationDrafts = Object.fromEntries(Object.entries(drafts)
        .filter(([toolId, status]) => authoritative[toolId] !== undefined && authoritative[toolId] !== status));
    }
  };

  reconcileAuthoritativePromptActivations = (
    connectorId: string,
    prompts: Array<{ prompt_id: string; activation_status: CapabilityActivationStatus }>
  ): void => {
    const authoritative = Object.fromEntries(prompts.map((prompt) => [prompt.prompt_id, prompt.activation_status]));
    const drafts = { ...this.promptActivationDrafts };
    this.markPromptActivationsSaved(connectorId, authoritative);
    if (this.selectedConnectorId === connectorId) {
      this.promptActivationDrafts = Object.fromEntries(Object.entries(drafts)
        .filter(([promptId, status]) => authoritative[promptId] !== undefined && authoritative[promptId] !== status));
    }
  };

  reconcileAuthoritativeResourceActivations = (
    connectorId: string,
    resources: Array<{ resource_id: string; kind: 'resource' | 'resource_template'; activation_status: CapabilityActivationStatus }>
  ): void => {
    const authoritative = Object.fromEntries(
      resources.map((resource) => [resourceActivationKey(resource.kind, resource.resource_id), resource.activation_status])
    );
    const drafts = { ...this.resourceActivationDrafts };
    this.markResourceActivationsSaved(connectorId, authoritative);
    if (this.selectedConnectorId === connectorId) {
      this.resourceActivationDrafts = Object.fromEntries(Object.entries(drafts)
        .filter(([key, status]) => authoritative[key] !== undefined && authoritative[key] !== status));
    }
  };

  markToolActivationsSaved = (connectorId: string, changes: Record<string, ConnectorToolActivationStatus>): void => {
    this.connectors = this.connectors.map((connector) => {
      if (connector.id !== connectorId) return connector;
      return {
        ...connector,
        tools: connector.tools.map((tool) => ({
          ...tool,
          activationStatus: changes[tool.operationName] ?? tool.activationStatus
        }))
      };
    });
    this.selection.updateDetail(connectorId, (cached) => ({
      ...cached,
      detail: {
        ...cached.detail,
        tools: cached.detail.tools.map((tool) => ({
          ...tool,
          activationStatus: changes[tool.operationName] ?? tool.activationStatus
        }))
      }
    }));
    if (this.selectedConnectorId === connectorId) this.resetToolActivationDrafts();
  };

  markPromptActivationsSaved = (connectorId: string, changes: Record<string, CapabilityActivationStatus>): void => {
    this.selection.updateDetail(connectorId, (cached) => ({
      ...cached,
      promptCatalog: {
        ...cached.promptCatalog,
        prompts: cached.promptCatalog.prompts.map((prompt) => ({
          ...prompt,
          activation_status: changes[prompt.name] ?? prompt.activation_status
        }))
      }
    }));
    if (this.selectedConnectorId === connectorId) this.resetPromptActivationDrafts();
  };

  markResourceActivationsSaved = (connectorId: string, changes: Record<string, CapabilityActivationStatus>): void => {
    this.selection.updateDetail(connectorId, (cached) => ({
      ...cached,
      resourceCatalog: {
        ...cached.resourceCatalog,
        resources: cached.resourceCatalog.resources.map((resource) => {
          const resourceId = resource.kind === 'resource' ? resource.uri : resource.uriTemplate;
          const key = resourceActivationKey(resource.kind, resourceId);
          return {
            ...resource,
            activationStatus: changes[key] ?? resource.activationStatus
          };
        })
      }
    }));
    if (this.selectedConnectorId === connectorId) this.resetResourceActivationDrafts();
  };

  replaceConnectors = (connectors: ConnectorListItem[]): void => {
    this.connectors = connectors;
    this.selection.replaceItems(connectors);
  };

  requestPublicationConfirmation = (
    form: HTMLFormElement,
    connectorName: string,
    actionLabel: PublicationActionLabel
  ): void => {
    this.pendingPublication = {
      form,
      connectorName,
      actionLabel
    };
  };

  cancelPublication = (): void => {
    this.pendingPublication = null;
    this.openMenuConnectorId = null;
  };

  confirmPublication = (): void => {
    const form = this.pendingPublication?.form;
    form?.requestSubmit();
    this.pendingPublication = null;
    this.openMenuConnectorId = null;
  };
}
