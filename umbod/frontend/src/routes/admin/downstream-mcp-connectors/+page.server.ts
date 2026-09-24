import { fail, redirect, type Actions } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { presentDownstreamMcpActionError } from '$lib/admin/downstream-mcp-errors';
import { downstreamMcpConnectorCreateInputSchema, downstreamMcpConnectorMetadataPatchSchema, downstreamMcpConnectorConfigurationInputSchema, downstreamMcpToolActivationBatchRequestSchema, type DownstreamMcpConnectorCreateInput } from '$lib/admin/downstream-mcp-connectors';
import { invocationPolicyBatchUpdateRequestSchema, invocationPolicyConflictResponseSchema } from '$lib/admin/invocation-policy';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { PageServerLoad } from './$types';
import { mapResourceCatalog, promptActivationBatchRequestSchema, resourceActivationBatchRequestSchema } from '$lib/admin/capability-catalogs';
import { loadSelectedDetail } from '$lib/admin/selected-detail-facade';
import { presentSaveFailureWithReconciliation } from '$lib/admin/tool-activation-reconciliation';

function location(connectorId?: string): string {
  return connectorId ? `/admin/downstream-mcp-connectors?connector=${encodeURIComponent(connectorId)}` : '/admin/downstream-mcp-connectors';
}

function presentActionFailure(error: unknown, action: string) {
  const presented = presentDownstreamMcpActionError(error, action);
  return fail(presented.statusCode, presented.data);
}

function connectorFields(data: FormData) {
  const submittedPath = String(data.get('publicPath') ?? '').trim();
  const publicPath = submittedPath.startsWith('/mcp/proxies/') ? submittedPath : `/mcp/proxies/${submittedPath.replace(/^\/+/, '')}`;
  return {
    display_name: String(data.get('displayName') ?? '').trim(),
    tool_name_prefix: String(data.get('toolNamePrefix') ?? '').trim(),
    capability_description: String(data.get('capabilityDescription') ?? '').trim(),
    endpoint_url: String(data.get('endpointUrl') ?? '').trim(),
    public_path: publicPath
  };
}

function createConnectorInput(data: FormData): DownstreamMcpConnectorCreateInput | null {
  const requestedMode = String(data.get('authMode') ?? 'none');
  if (requestedMode !== 'none' && requestedMode !== 'static_bearer') return null;
  const authMode = requestedMode;
  const { endpoint_url, ...metadata } = connectorFields(data);
  const headerType = String(data.get('headerType') ?? 'bearer');
  const configuration = authMode === 'static_bearer'
    ? { endpoint_url, auth_mode: 'static_bearer' as const, header_type: headerType, custom_header_name: headerType === 'custom' ? String(data.get('customHeaderName') ?? '') : null, bearer_token: String(data.get('bearerToken') ?? '') }
    : { endpoint_url, auth_mode: authMode, header_type: null, custom_header_name: null, bearer_token: null };
  const candidate = {
    metadata,
    configuration,
    capability_description_override: { state: 'system' as const }
  };
  const parsed = downstreamMcpConnectorCreateInputSchema.safeParse(candidate);
  return parsed.success ? parsed.data : null;
}

function updateConnectorInput(data: FormData) {
  const requestedMode = String(data.get('authMode') ?? 'none');
  if (requestedMode !== 'none' && requestedMode !== 'static_bearer') return null;
  const authMode = requestedMode;
  const fields = connectorFields(data);
  const metadata = downstreamMcpConnectorMetadataPatchSchema.safeParse({ display_name: fields.display_name, tool_name_prefix: fields.tool_name_prefix, capability_description: fields.capability_description, public_path: fields.public_path });
  const token = String(data.get('bearerToken') ?? '');
  const headerType = String(data.get('headerType') ?? 'bearer');
  const configuration = downstreamMcpConnectorConfigurationInputSchema.safeParse(authMode === 'static_bearer' ? { endpoint_url: fields.endpoint_url, auth_mode: 'static_bearer', header_type: headerType, custom_header_name: headerType === 'custom' ? String(data.get('customHeaderName') ?? '') : null, bearer_token: token || null } : { endpoint_url: fields.endpoint_url, auth_mode: authMode, header_type: null, custom_header_name: null, bearer_token: null });
  return metadata.success && configuration.success ? { metadata: metadata.data, configuration: configuration.data } : null;
}

export const load: PageServerLoad = async (event) => {
  const api = adminServerApi(event).downstreamMcpConnectors;
  const result = await api.list();
  const detail = await loadSelectedDetail({
    summaries: result.connectors,
    requestedId: event.url.searchParams.get('connector'),
    idOf: (connector) => connector.connector_id,
    loadDetail: async (id) => {
      const bundle = await Promise.all([api.get(id), api.tools(id), api.prompts(id), api.resources(id), api.listActivations(id)]);
      const invocationPolicies = bundle[4].tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision }));
      return { selectedDetail: bundle[0], catalog: bundle[1], promptCatalog: bundle[2], resourceCatalog: mapResourceCatalog(bundle[3]), invocationPolicies };
    }
  });
  const selected = 'selectedDetail' in detail ? detail.selectedDetail : undefined;
  return { connectors: result.connectors, selectedConnectorId: detail.selectedId, selectedDetail: selected?.selectedDetail, catalog: selected?.catalog, promptCatalog: selected?.promptCatalog, resourceCatalog: selected?.resourceCatalog, invocationPolicies: selected?.invocationPolicies, selectedDetailFailed: 'selectedDetailFailed' in detail };
};

export const actions: Actions = {
  create: async (event) => {
    const data = await event.request.formData();
    const values = {
      displayName: String(data.get('displayName') ?? '').trim(),
      toolNamePrefix: String(data.get('toolNamePrefix') ?? '').trim(),
      capabilityDescription: String(data.get('capabilityDescription') ?? '').trim(),
      endpointUrl: String(data.get('endpointUrl') ?? '').trim(),
      publicPath: connectorFields(data).public_path,
      authMode: String(data.get('authMode') ?? 'none'),
      headerType: String(data.get('headerType') ?? 'bearer'),
      customHeaderName: String(data.get('customHeaderName') ?? '')
    };
    const input = createConnectorInput(data);
    if (!input) {
      const message = values.publicPath === '/mcp'
        ? 'The shared /mcp endpoint cannot be assigned to one connector. Use a dedicated path such as /mcp/proxies/computerlove-tech; enabled tools can still be published on /mcp.'
        : 'Complete all required fields. The dedicated path must start with /mcp/proxies/ and the downstream endpoint must use HTTPS.';
      return fail(422, { status: 'invalid', mode: 'create', message, values });
    }
    let connector;
    try {
      connector = await adminServerApi(event).downstreamMcpConnectors.create(input);
    } catch (error) {
      const presented = presentDownstreamMcpActionError(error, 'Connector creation');
      return fail(presented.statusCode, { ...presented.data, mode: 'create', values });
    }
    redirect(303, location(connector.connector_id));
  },
  configure: async (event) => {
    const data = await event.request.formData();
    const connectorId = String(data.get('connectorId') ?? '');
    const input = updateConnectorInput(data);
    if (!input) return fail(422, { status: 'invalid', message: 'Check the configuration values.' });
    try {
      await adminServerApi(event).downstreamMcpConnectors.patchMetadata(connectorId, input.metadata);
    } catch (error) {
      return presentActionFailure(error, 'Metadata was not saved. Configuration was not changed.');
    }
    try {
      await adminServerApi(event).downstreamMcpConnectors.putConfiguration(connectorId, input.configuration);
    } catch (error) {
      return presentActionFailure(error, 'Metadata was saved, but configuration failed. Review the preserved values and try again.');
    }
    redirect(303, location(connectorId));
  },
  refresh: async (event) => {
    const data = await event.request.formData(); const id = String(data.get('connectorId') ?? '');
    let connector;
    try { connector = await adminServerApi(event).downstreamMcpConnectors.discover(id); } catch (error) { return presentActionFailure(error, 'Discovery'); }
    if (connector.health.status === 'unhealthy') return fail(422, { status: 'unhealthy', message: connector.health.reason ?? 'Discovery completed but the downstream server is unhealthy.' });
    redirect(303, location(id));
  },
  publish: async (event) => {
    const id = String((await event.request.formData()).get('connectorId') ?? '');
    try { await adminServerApi(event).downstreamMcpConnectors.publish(id); } catch (error) { return presentActionFailure(error, 'Publication'); }
    redirect(303, location(id));
  },
  unpublish: async (event) => {
    const id = String((await event.request.formData()).get('connectorId') ?? '');
    try { await adminServerApi(event).downstreamMcpConnectors.unpublish(id); } catch (error) { return presentActionFailure(error, 'Unpublication'); }
    redirect(303, location(id));
  },
  saveToolActivations: async (event) => {
    const data = await event.request.formData();
    const connectorId = String(data.get('connectorId') ?? '');
    let candidate: unknown;
    try { candidate = JSON.parse(String(data.get('toolActivations') ?? '')); }
    catch { return fail(422, { status: 'invalid', message: 'Tool activation changes are invalid.' }); }
    const activationTools = typeof candidate === 'object' && candidate !== null && 'tools' in candidate && Array.isArray(candidate.tools) ? candidate.tools : [];
    const parsed = activationTools.length > 0 ? downstreamMcpToolActivationBatchRequestSchema.safeParse(candidate) : null;
    let policyCandidate: unknown;
    try { policyCandidate = JSON.parse(String(data.get('invocationPolicies') ?? '')); }
    catch { return fail(422, { status: 'invalid', message: 'Invocation policy changes are invalid.' }); }
    const policyTools = typeof policyCandidate === 'object' && policyCandidate !== null && 'tools' in policyCandidate && Array.isArray(policyCandidate.tools) ? policyCandidate.tools : [];
    const policies = policyTools.length > 0 ? invocationPolicyBatchUpdateRequestSchema.safeParse(policyCandidate) : null;
    if (!connectorId || (parsed && !parsed.success) || (policies && !policies.success) || (!parsed && !policies)) return fail(422, { status: 'invalid', message: 'Tool changes are invalid.' });
    try {
      const changes = new Map<string, { toolId: string; activationStatus?: 'enabled' | 'disabled'; invocationMode?: 'direct' | 'ask'; expectedPolicyRevision?: number }>();
      parsed?.data.tools.forEach((tool) => changes.set(tool.tool_id, { toolId: tool.tool_id, activationStatus: tool.activation_status }));
      policies?.data.tools.forEach((tool) => changes.set(tool.tool_id, { ...changes.get(tool.tool_id), toolId: tool.tool_id, invocationMode: tool.mode, expectedPolicyRevision: tool.expected_revision }));
      const response = await adminServerApi(event).downstreamMcpConnectors.saveActivations(connectorId, [...changes.values()]);
      const activationToolIds = new Set(parsed?.data.tools.map((tool) => tool.tool_id) ?? []);
      const policyToolIds = new Set(policies?.data.tools.map((tool) => tool.tool_id) ?? []);
      const activationResponse = { ...response, tools: response.tools.filter((tool) => activationToolIds.has(tool.tool_id)) };
      const policyResponse = { connector_kind: 'downstream_mcp' as const, connector_id: connectorId, tools: response.tools.filter((tool) => policyToolIds.has(tool.tool_id)).map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) };
      return { activationResponse, policyResponse };
    } catch (error) {
      const conflict = error instanceof HttpError && error.status === 409 ? invocationPolicyConflictResponseSchema.safeParse(error.body) : undefined;
      const failure = conflict?.success ? undefined : presentActionFailure(error, 'Tool activation');
      const original = conflict?.success
        ? { status: 409, data: { status: 'conflict' as const, connectorId, message: 'Invocation policies changed by another administrator.', policyConflicts: conflict.data.conflicts } }
        : { status: failure!.status, data: { ...failure!.data, connectorId } };
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => original,
        loadAuthoritative: () => adminServerApi(event).downstreamMcpConnectors.listActivations(connectorId),
        presentAuthoritative: (authoritativeActivationResponse) => ({
          authoritativeActivationResponse,
          authoritativePolicyResponse: { connector_kind: 'downstream_mcp' as const, connector_id: connectorId, tools: authoritativeActivationResponse.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) }
        })
      });
      return fail(presented.status, presented.data);
    }
  },
  savePromptActivations: async (event) => {
    const data = await event.request.formData();
    const connectorId = String(data.get('connectorId') ?? '');
    let candidate: unknown;
    try { candidate = JSON.parse(String(data.get('promptActivations') ?? '')); }
    catch { return fail(422, { status: 'invalid', message: 'Prompt activation changes are invalid.' }); }
    const prompts = Array.isArray(candidate) ? candidate : [];
    const parsed = promptActivationBatchRequestSchema.safeParse({ prompts });
    if (!connectorId || !parsed.success) return fail(422, { status: 'invalid', message: 'Prompt activation changes are invalid.' });
    try {
      const activationResponse = await adminServerApi(event).downstreamMcpConnectors.savePromptActivations(connectorId, parsed.data);
      return { activationResponse };
    } catch (error) {
      const failure = presentActionFailure(error, 'Prompt activation');
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => ({ status: failure.status, data: { ...failure.data, connectorId } }),
        loadAuthoritative: () => adminServerApi(event).downstreamMcpConnectors.prompts(connectorId),
        presentAuthoritative: (catalog) => ({
          authoritativePromptResponse: {
            connector_id: connectorId,
            prompts: catalog.prompts.map((prompt) => ({ prompt_id: prompt.name, activation_status: prompt.activation_status }))
          }
        })
      });
      return fail(presented.status, presented.data);
    }
  },
  saveResourceActivations: async (event) => {
    const data = await event.request.formData();
    const connectorId = String(data.get('connectorId') ?? '');
    let candidate: unknown;
    try { candidate = JSON.parse(String(data.get('resourceActivations') ?? '')); }
    catch { return fail(422, { status: 'invalid', message: 'Resource activation changes are invalid.' }); }
    const resources = Array.isArray(candidate) ? candidate : [];
    const parsed = resourceActivationBatchRequestSchema.safeParse({ resources });
    if (!connectorId || !parsed.success) return fail(422, { status: 'invalid', message: 'Resource activation changes are invalid.' });
    try {
      const activationResponse = await adminServerApi(event).downstreamMcpConnectors.saveResourceActivations(connectorId, parsed.data);
      return { activationResponse };
    } catch (error) {
      const failure = presentActionFailure(error, 'Resource activation');
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => ({ status: failure.status, data: { ...failure.data, connectorId } }),
        loadAuthoritative: () => adminServerApi(event).downstreamMcpConnectors.resources(connectorId),
        presentAuthoritative: (catalog) => ({
          authoritativeResourceResponse: {
            connector_id: connectorId,
            resources: catalog.resources.map((resource) => ({
              resource_id: resource.uri,
              kind: resource.kind,
              activation_status: resource.activation_status
            }))
          }
        })
      });
      return fail(presented.status, presented.data);
    }
  },
  delete: async (event) => {
    const id = String((await event.request.formData()).get('connectorId') ?? '');
    let nextConnectorId: string | undefined;
    try {
      const api = adminServerApi(event).downstreamMcpConnectors;
      await api.delete(id);
      nextConnectorId = (await api.list()).connectors[0]?.connector_id;
    } catch (error) { return presentActionFailure(error, 'Deletion'); }
    redirect(303, location(nextConnectorId));
  }
};
