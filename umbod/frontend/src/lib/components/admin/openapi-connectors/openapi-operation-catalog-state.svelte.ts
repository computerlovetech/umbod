import type { OpenApiOperationToolUiModel, OpenApiToolActivationBatchRequest, OpenApiToolActivationBatchResponse } from '$lib/admin/openapi-connectors';
import type { InvocationPolicyMode, InvocationPolicyTool } from '$lib/admin/invocation-policy';

export const openApiOperationStatusFilters = ['all', 'enabled', 'disabled'] as const;
export const openApiOperationPageSizes = [20, 50, 100] as const;

export type OpenApiOperationMethodFilter = string;
export type OpenApiOperationStatusFilter = (typeof openApiOperationStatusFilters)[number];
export type OpenApiOperationPageSize = (typeof openApiOperationPageSizes)[number];

export class OpenApiOperationCatalogState {
  search = $state('');
  methodFilter = $state<OpenApiOperationMethodFilter>('all');
  statusFilter = $state<OpenApiOperationStatusFilter>('all');
  pageSize = $state<OpenApiOperationPageSize>(20);
  page = $state(1);
  tools: OpenApiOperationToolUiModel[];
  persistedStatuses: Record<string, OpenApiOperationToolUiModel['activationStatus']>;
  pending = $state(false);
  submittedTools: OpenApiToolActivationBatchRequest['tools'] = [];
  policies: Record<string, InvocationPolicyTool>;
  persistedPolicies: Record<string, InvocationPolicyTool>;
  conflicts = $state.raw<Record<string, boolean>>({});
  availableMethods = $derived.by(() =>
    [...new Set(this.tools.map((tool) => this.normalizeMethod(tool.method)))].sort()
  );
  filteredTools = $derived.by(() => {
    const query = this.search.trim().toLowerCase();
    const normalizedMethodFilter = this.normalizeMethod(this.methodFilter);
    return this.tools.filter((tool) => {
      const matchesSearch = !query || [tool.operationId, tool.method, tool.path, tool.summary, tool.description]
        .some((value) => value.toLowerCase().includes(query));
      const matchesMethod = this.methodFilter === 'all' || this.normalizeMethod(tool.method) === normalizedMethodFilter;
      const matchesStatus = this.statusFilter === 'all' || tool.activationStatus === this.statusFilter;
      return matchesSearch && matchesMethod && matchesStatus;
    });
  });
  changedTools = $derived.by(() => this.tools.filter((tool) => this.persistedStatuses[tool.operationId] !== tool.activationStatus).map((tool) => ({ tool_id: tool.operationId, activation_status: tool.activationStatus })));
  changedPolicies = $derived.by(() => Object.values(this.policies).filter((policy) => this.persistedPolicies[policy.tool_id]?.mode !== policy.mode).map((policy) => ({ tool_id: policy.tool_id, mode: policy.mode, expected_revision: this.persistedPolicies[policy.tool_id].revision })));
  dirty = $derived(this.changedTools.length > 0 || this.changedPolicies.length > 0);
  totalCount = $derived.by(() => this.tools.length);
  filteredCount = $derived.by(() => this.filteredTools.length);
  pageCount = $derived.by(() => Math.max(1, Math.ceil(this.filteredCount / this.pageSize)));
  paginatedTools = $derived.by(() => {
    const start = (this.page - 1) * this.pageSize;
    return this.filteredTools.slice(start, start + this.pageSize);
  });
  canGoPrevious = $derived(this.page > 1);
  canGoNext = $derived(this.page < this.pageCount);

  constructor(tools: OpenApiOperationToolUiModel[], policies: InvocationPolicyTool[] = []) {
    this.tools = $state(tools);
    this.persistedStatuses = $state(Object.fromEntries(tools.map((tool) => [tool.operationId, tool.activationStatus])));
    this.policies = $state(Object.fromEntries(policies.map((policy) => [policy.tool_id, policy])));
    this.persistedPolicies = $state(Object.fromEntries(policies.map((policy) => [policy.tool_id, policy])));
  }

  policyMode = (toolId: string): InvocationPolicyMode => this.policies[toolId]?.mode ?? 'direct';
  setPolicy = (toolId: string, mode: InvocationPolicyMode): void => {
    if (!this.pending && this.policies[toolId]) this.policies = { ...this.policies, [toolId]: { ...this.policies[toolId], mode } };
  };
  policyRequestJson = (): string => JSON.stringify({ tools: this.changedPolicies });
  reconcilePolicies = (policies: InvocationPolicyTool[], conflict = false): void => {
    const incoming = Object.fromEntries(policies.map((policy) => [policy.tool_id, policy]));
    this.persistedPolicies = { ...this.persistedPolicies, ...incoming };
    if (!conflict) this.policies = { ...this.policies, ...incoming };
    this.conflicts = conflict ? Object.fromEntries(policies.map((policy) => [policy.tool_id, true])) : {};
  };

  reconcileAuthoritativePolicies = (policies: InvocationPolicyTool[]): void => {
    const incoming = Object.fromEntries(policies.map((policy) => [policy.tool_id, policy]));
    const drafts = Object.fromEntries(Object.values(this.policies)
      .filter((policy) => incoming[policy.tool_id] && incoming[policy.tool_id].mode !== policy.mode)
      .map((policy) => [policy.tool_id, { ...incoming[policy.tool_id], mode: policy.mode }]));
    this.persistedPolicies = incoming;
    this.policies = { ...incoming, ...drafts };
  };

  reconcileAuthoritativeActivations = (response: OpenApiToolActivationBatchResponse): void => {
    this.persistedStatuses = Object.fromEntries(response.tools.map((tool) => [tool.tool_id, tool.activation_status]));
    this.tools = this.tools.map((tool) => {
      const authoritative = this.persistedStatuses[tool.operationId];
      return authoritative === undefined || tool.activationStatus !== authoritative ? tool : { ...tool, activationStatus: authoritative };
    });
  };

  private normalizeMethod(method: string): string {
    return method.trim().toUpperCase();
  }

  setSearch = (search: string) => {
    this.search = search;
    this.page = 1;
  };

  setMethodFilter = (methodFilter: OpenApiOperationMethodFilter) => {
    this.methodFilter = methodFilter;
    this.page = 1;
  };

  setStatusFilter = (statusFilter: OpenApiOperationStatusFilter) => {
    this.statusFilter = statusFilter;
    this.page = 1;
  };

  setPageSize = (pageSize: OpenApiOperationPageSize) => {
    this.pageSize = pageSize;
    this.page = 1;
  };

  previousPage = () => {
    this.page = Math.max(1, this.page - 1);
  };

  nextPage = () => {
    this.page = Math.min(this.pageCount, this.page + 1);
  };

  setToolActivation = (operationId: string, activationStatus: 'enabled' | 'disabled'): void => {
    if (this.pending) return;
    this.tools = this.tools.map((tool) =>
      tool.operationId === operationId ? { ...tool, activationStatus } : tool
    );
    this.page = Math.min(this.page, this.pageCount);
  };

  beginSave = (): void => {
    this.submittedTools = [...this.changedTools];
    this.pending = true;
  };

  finishSave = (response?: OpenApiToolActivationBatchResponse): OpenApiOperationToolUiModel[] | undefined => {
    const submittedStatuses = new Map(this.submittedTools.map((tool) => [tool.tool_id, tool.activation_status]));
    const responseIds = response?.tools.map((tool) => tool.tool_id) ?? [];
    const responseMatchesSubmission = response !== undefined
      && response.tools.length === this.submittedTools.length
      && new Set(responseIds).size === responseIds.length
      && response.tools.every((tool) => submittedStatuses.get(tool.tool_id) === tool.activation_status);
    const savedTools = responseMatchesSubmission
      ? this.tools.filter((tool) => submittedStatuses.get(tool.operationId) === tool.activationStatus)
      : undefined;
    if (responseMatchesSubmission && response) {
      this.persistedStatuses = {
        ...this.persistedStatuses,
        ...Object.fromEntries(response.tools.map((tool) => [tool.tool_id, tool.activation_status]))
      };
    }
    this.submittedTools = [];
    this.pending = false;
    return savedTools;
  };

  activationRequestJson = (): string => JSON.stringify({ tools: this.changedTools });
}
