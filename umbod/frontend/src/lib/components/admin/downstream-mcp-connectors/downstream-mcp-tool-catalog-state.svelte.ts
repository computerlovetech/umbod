import type { DownstreamMcpTool, DownstreamMcpToolActivationBatchRequest, DownstreamMcpToolActivationBatchResponse } from '$lib/admin/downstream-mcp-connectors';
import type { InvocationPolicyMode, InvocationPolicyTool } from '$lib/admin/invocation-policy';

export const downstreamMcpToolStatusFilters = ['all', 'enabled', 'disabled'] as const;
export const downstreamMcpToolPageSizes = [20, 50, 100] as const;
export type DownstreamMcpToolStatusFilter = (typeof downstreamMcpToolStatusFilters)[number];
export type DownstreamMcpToolPageSize = (typeof downstreamMcpToolPageSizes)[number];

export class DownstreamMcpToolCatalogState {
  search = $state('');
  statusFilter = $state<DownstreamMcpToolStatusFilter>('all');
  pageSize = $state<DownstreamMcpToolPageSize>(20);
  page = $state(1);
  tools: DownstreamMcpTool[];
  persistedStatuses: Record<string, DownstreamMcpTool['activation_status']>;
  pending = $state(false);
  policies: Record<string, InvocationPolicyTool>;
  persistedPolicies: Record<string, InvocationPolicyTool>;
  submittedTools: DownstreamMcpToolActivationBatchRequest['tools'] = [];
  conflicts = $state.raw<Record<string, boolean>>({});
  filteredTools = $derived.by(() => {
    const query = this.search.trim().toLowerCase();
    return this.tools.filter((tool) => {
      const matchesSearch = !query || [tool.name, tool.title, tool.description].some((value) => value.toLowerCase().includes(query));
      const matchesStatus = this.statusFilter === 'all' || tool.activation_status === this.statusFilter;
      return matchesSearch && matchesStatus;
    });
  });
  changedTools = $derived.by(() => this.tools.filter((tool) => this.persistedStatuses[tool.name] !== tool.activation_status).map((tool) => ({ tool_id: tool.name, activation_status: tool.activation_status })));
  changedPolicies = $derived.by(() => Object.values(this.policies).filter((policy) => this.persistedPolicies[policy.tool_id]?.mode !== policy.mode).map((policy) => ({ tool_id: policy.tool_id, mode: policy.mode, expected_revision: this.persistedPolicies[policy.tool_id].revision })));
  dirty = $derived(this.changedTools.length > 0 || this.changedPolicies.length > 0);
  totalCount = $derived.by(() => this.tools.length);
  filteredCount = $derived(this.filteredTools.length);
  pageCount = $derived(Math.max(1, Math.ceil(this.filteredCount / this.pageSize)));
  paginatedTools = $derived.by(() => this.filteredTools.slice((this.page - 1) * this.pageSize, this.page * this.pageSize));
  canGoPrevious = $derived(this.page > 1);
  canGoNext = $derived(this.page < this.pageCount);

  constructor(tools: DownstreamMcpTool[], policies: InvocationPolicyTool[] = []) {
    this.tools = $state(tools);
    this.persistedStatuses = $state(Object.fromEntries(tools.map((tool) => [tool.name, tool.activation_status])));
    this.policies = $state(Object.fromEntries(policies.map((policy) => [policy.tool_id, policy])));
    this.persistedPolicies = $state(Object.fromEntries(policies.map((policy) => [policy.tool_id, policy])));
  }
  policyMode = (toolId: string): InvocationPolicyMode => this.policies[toolId]?.mode ?? 'direct';
  setPolicy = (toolId: string, mode: InvocationPolicyMode): void => { if (!this.pending && this.policies[toolId]) this.policies = { ...this.policies, [toolId]: { ...this.policies[toolId], mode } }; };
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
  reconcileAuthoritativeActivations = (response: DownstreamMcpToolActivationBatchResponse): void => {
    this.persistedStatuses = Object.fromEntries(response.tools.map((tool) => [tool.tool_id, tool.activation_status]));
  };
  setSearch = (search: string): void => { this.search = search; this.page = 1; };
  setStatusFilter = (statusFilter: DownstreamMcpToolStatusFilter): void => { this.statusFilter = statusFilter; this.page = 1; };
  setPageSize = (pageSize: DownstreamMcpToolPageSize): void => { this.pageSize = pageSize; this.page = 1; };
  setToolActivation = (name: string, activationStatus: DownstreamMcpTool['activation_status']): void => {
    if (this.pending) return;
    this.tools = this.tools.map((tool) => tool.name === name ? { ...tool, activation_status: activationStatus } : tool);
  };
  beginSave = (): void => { this.submittedTools = [...this.changedTools]; this.pending = true; };
  finishSave = (response?: DownstreamMcpToolActivationBatchResponse): void => {
    if (response) {
      this.persistedStatuses = {
        ...this.persistedStatuses,
        ...Object.fromEntries(response.tools.map((tool) => [tool.tool_id, tool.activation_status]))
      };
    }
    this.submittedTools = [];
    this.pending = false;
  };
  activationRequestJson = (): string => JSON.stringify({ tools: this.changedTools });
  previousPage = (): void => { this.page = Math.max(1, this.page - 1); };
  nextPage = (): void => { this.page = Math.min(this.pageCount, this.page + 1); };
}
