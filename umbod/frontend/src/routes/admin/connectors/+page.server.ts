import { mapResourceCatalog, promptActivationBatchRequestSchema, resourceActivationBatchRequestSchema } from '$lib/admin/capability-catalogs';
import { HttpError, isOperationalError } from '$lib/admin/infrastructure/transport';
import { invocationPolicyBatchUpdateRequestSchema, invocationPolicyConflictResponseSchema } from '$lib/admin/invocation-policy';
import { connectorToolActivationBatchRequestSchema } from '$lib/admin/connectors';
import { fail } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import type { Actions, PageServerLoad } from './$types';
import {
  checkConnectorConfiguration,
  publishConnector,
  saveConnectorConfiguration,
  unpublishConnector
} from '$lib/admin/connectors-api';
import { mapConnectorApiItem, mapConnectorConfigurationApiResponse, mapConnectorDetailApiResponse } from '$lib/admin/connectors';
import {
  connectorIdFromRequest,
  createConfigurationBody,
  createFailureValues,
  getSecretFields
} from '$lib/admin/connectors-forms';
import { loadSelectedDetail } from '$lib/admin/selected-detail-facade';
import { presentSaveFailureWithReconciliation } from '$lib/admin/tool-activation-reconciliation';

type ConnectorConfigurationActionInput = {
  connectorId: string;
  configuration: Record<string, string>;
  values: Record<string, string>;
};

export const load: PageServerLoad = async (event) => {
  const api = adminServerApi(event).connectors;
  try {
    const response = await api.connectors.list();
    const allConnectors = response.connectors.map(mapConnectorApiItem);
    if (allConnectors.length === 0) return { status: 'empty' as const, message: 'No connectors are currently available', connectors: [] };
    const successMessage = configuredSuccessMessage(allConnectors, event.url.searchParams.get('configured'));
    const requestedConnectorId = event.url.searchParams.get('connector');
    const requestedConnector = allConnectors.find((connector) => connector.id === requestedConnectorId);
    if (requestedConnector && !requestedConnector.isConfigured) {
      try {
        const configuration = mapConnectorConfigurationApiResponse(await api.connectors.getConfiguration(requestedConnector.id));
        const connectors = allConnectors.map((connector) => connector.id === requestedConnector.id
          ? { ...connector, configurationFields: configuration.fields }
          : connector);
        return { status: 'ready' as const, connectors, selectedConnectorId: requestedConnector.id, successMessage };
      } catch (error) {
        if (!isOperationalError(error)) throw error;
        return { status: 'ready' as const, connectors: allConnectors, selectedConnectorId: requestedConnector.id, selectedDetailFailed: true as const, successMessage };
      }
    }
    const selected = await loadSelectedDetail({
      summaries: allConnectors,
      requestedId: event.url.searchParams.get('connector'),
      idOf: (connector) => connector.id,
      loadDetail: async (id) => {
        const [detail, activation, configuration, prompts, resources] = await Promise.all([api.connectors.get(id), api.tools.listActivations(id), api.connectors.getConfiguration(id), api.prompts.list(id), api.resources.list(id)]);
        const invocationPolicies = activation.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision }));
        return { detail: mapConnectorDetailApiResponse(detail, activation), configuration: mapConnectorConfigurationApiResponse(configuration), promptCatalog: prompts, resourceCatalog: mapResourceCatalog(resources), invocationPolicies };
      },
      eligible: (connector) => connector.isConfigured
    });
    if (selected.selectedId === undefined) return { status: 'ready' as const, connectors: allConnectors, successMessage };
    if ('selectedDetailFailed' in selected) return { status: 'ready' as const, connectors: allConnectors, selectedConnectorId: selected.selectedId, selectedDetailFailed: true as const, successMessage };
    const connectors = allConnectors.map((connector) => connector.id === selected.selectedId
      ? { ...connector, tools: selected.selectedDetail.detail.status === 'ready' ? selected.selectedDetail.detail.tools : [], configurationFields: selected.selectedDetail.configuration.status === 'ready' ? selected.selectedDetail.configuration.fields : undefined }
      : connector);
    return { status: 'ready' as const, connectors, selectedConnectorId: selected.selectedId, selectedDetail: selected.selectedDetail.detail, selectedPromptCatalog: selected.selectedDetail.promptCatalog, selectedResourceCatalog: selected.selectedDetail.resourceCatalog, invocationPolicies: selected.selectedDetail.invocationPolicies, successMessage };
  } catch (error) {
    if (!isOperationalError(error)) throw error;
    return { status: 'failed' as const, message: 'Failed to get connectors', retryLabel: 'Try again', connectors: [] };
  }
};

function configuredSuccessMessage(connectors: ReturnType<typeof mapConnectorApiItem>[], configuredConnectorId: string | null): string | null {
  const configuredConnector = connectors.find((connector) => connector.id === configuredConnectorId);
  return configuredConnector ? `${configuredConnector.name} was configured successfully` : null;
}

export const actions: Actions = {
  publish: async (event) => publishConnector(adminServerApi(event).connectors, await connectorIdFromRequest(event.request)),
  unpublish: async (event) => unpublishConnector(adminServerApi(event).connectors, await connectorIdFromRequest(event.request)),
  saveToolActivations: async (event) => {
    const data = await event.request.formData();
    const connectorId = String(data.get('connectorId') ?? '');
    let activations: unknown;
    let policies: unknown;
    try { activations = JSON.parse(String(data.get('toolActivations') ?? '')); policies = JSON.parse(String(data.get('invocationPolicies') ?? '')); } catch { return fail(422, { status: 'invalid', message: 'Tool changes are invalid.' }); }
    const activationTools = Array.isArray(activations) ? activations.map((tool) => typeof tool === 'object' && tool !== null ? { tool_id: String(tool.operationName ?? ''), activation_status: tool.activationStatus } : tool) : [];
    const activationInput = activationTools.length ? connectorToolActivationBatchRequestSchema.safeParse({ tools: activationTools }) : null;
    const policyTools = typeof policies === 'object' && policies !== null && 'tools' in policies && Array.isArray(policies.tools) ? policies.tools : [];
    const policyInput = policyTools.length ? invocationPolicyBatchUpdateRequestSchema.safeParse(policies) : null;
    if (!connectorId || (!activationInput && !policyInput) || (activationInput && !activationInput.success) || (policyInput && !policyInput.success)) return fail(422, { status: 'invalid', message: 'Tool changes are invalid.' });
    try {
      const changes = new Map<string, { toolId: string; activationStatus?: 'enabled' | 'disabled'; invocationMode?: 'direct' | 'ask'; expectedPolicyRevision?: number }>();
      activationInput?.data.tools.forEach((tool) => changes.set(tool.tool_id, { toolId: tool.tool_id, activationStatus: tool.activation_status }));
      policyInput?.data.tools.forEach((tool) => changes.set(tool.tool_id, { ...changes.get(tool.tool_id), toolId: tool.tool_id, invocationMode: tool.mode, expectedPolicyRevision: tool.expected_revision }));
      const response = await adminServerApi(event).connectors.tools.saveActivations(connectorId, [...changes.values()]);
      const activationToolIds = new Set(activationInput?.data.tools.map((tool) => tool.tool_id) ?? []);
      const policyToolIds = new Set(policyInput?.data.tools.map((tool) => tool.tool_id) ?? []);
      const activationResponse = { ...response, tools: response.tools.filter((tool) => activationToolIds.has(tool.tool_id)) };
      const policyResponse = { connector_kind: 'native' as const, connector_id: connectorId, tools: response.tools.filter((tool) => policyToolIds.has(tool.tool_id)).map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) };
      return { status: 'saved', connectorId, policyResponse, activationResponse };
    } catch (error) {
      const conflict = error instanceof HttpError && error.status === 409 ? invocationPolicyConflictResponseSchema.safeParse(error.body) : undefined;
      if (!conflict?.success && !isOperationalError(error)) throw error;
      const original = conflict?.success
        ? { status: 409, data: { status: 'conflict' as const, connectorId, message: 'Invocation policies changed by another administrator.', policyConflicts: conflict.data.conflicts } }
        : { status: 503, data: { status: 'failed' as const, connectorId, errorMessage: 'Tool changes could not be saved.' } };
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => original,
        loadAuthoritative: () => adminServerApi(event).connectors.tools.listActivations(connectorId),
        presentAuthoritative: (authoritativeActivationResponse) => ({
          authoritativeActivationResponse,
          authoritativePolicyResponse: { connector_kind: 'native' as const, connector_id: connectorId, tools: authoritativeActivationResponse.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) }
        })
      });
      return fail(presented.status, presented.data);
    }
  },
  savePromptActivations: async (event) => {
    const data = await event.request.formData();
    const connectorId = String(data.get('connectorId') ?? '');
    let activations: unknown;
    try { activations = JSON.parse(String(data.get('promptActivations') ?? '')); }
    catch { return fail(422, { status: 'invalid', message: 'Prompt changes are invalid.' }); }
    const prompts = Array.isArray(activations)
      ? activations.map((item) => typeof item === 'object' && item !== null
        ? { prompt_id: String((item as { promptId?: unknown }).promptId ?? ''), activation_status: (item as { activationStatus?: unknown }).activationStatus }
        : item)
      : [];
    const parsed = promptActivationBatchRequestSchema.safeParse({ prompts });
    if (!connectorId || !parsed.success) return fail(422, { status: 'invalid', message: 'Prompt changes are invalid.' });
    try {
      await adminServerApi(event).connectors.prompts.saveActivations(connectorId, parsed.data);
      return { status: 'saved', connectorId };
    } catch (error) {
      if (!isOperationalError(error)) throw error;
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => ({ status: 503, data: { status: 'failed' as const, connectorId, errorMessage: 'Prompt changes could not be saved.' } }),
        loadAuthoritative: () => adminServerApi(event).connectors.prompts.list(connectorId),
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
    let activations: unknown;
    try { activations = JSON.parse(String(data.get('resourceActivations') ?? '')); }
    catch { return fail(422, { status: 'invalid', message: 'Resource changes are invalid.' }); }
    const resources = Array.isArray(activations)
      ? activations.map((item) => typeof item === 'object' && item !== null
        ? {
            resource_id: String((item as { resourceId?: unknown }).resourceId ?? ''),
            kind: (item as { kind?: unknown }).kind,
            activation_status: (item as { activationStatus?: unknown }).activationStatus
          }
        : item)
      : [];
    const parsed = resourceActivationBatchRequestSchema.safeParse({ resources });
    if (!connectorId || !parsed.success) return fail(422, { status: 'invalid', message: 'Resource changes are invalid.' });
    try {
      await adminServerApi(event).connectors.resources.saveActivations(connectorId, parsed.data);
      return { status: 'saved', connectorId };
    } catch (error) {
      if (!isOperationalError(error)) throw error;
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => ({ status: 503, data: { status: 'failed' as const, connectorId, errorMessage: 'Resource changes could not be saved.' } }),
        loadAuthoritative: () => adminServerApi(event).connectors.resources.list(connectorId),
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
  checkConfiguration: async (event) => {
    const { connectorId, configuration, values } = await connectorConfigurationActionInput(event.request);
    const result = await checkConnectorConfiguration(adminServerApi(event).connectors, connectorId, configuration);

    if (result.status === 'valid') {
      return { status: 'check-valid', connectorId, successMessage: 'Configuration check passed', values };
    }

    if (result.status === 'invalid') {
      return { status: 'check-invalid', connectorId, errorMessage: result.message, fieldMessages: result.fieldMessages, values };
    }

    return { status: 'failed', connectorId, errorMessage: result.errorMessage, values };
  },
  saveConfiguration: async (event) => {
    const { connectorId, configuration, values } = await connectorConfigurationActionInput(event.request);
    const result = await saveConnectorConfiguration(adminServerApi(event).connectors, connectorId, configuration);

    if (result.status === 'failed') {
      return { status: 'failed', connectorId, errorMessage: result.errorMessage, values };
    }

    return { status: 'saved', connectorId, successMessage: `${connectorId} was configured successfully` };
  }
};

async function connectorConfigurationActionInput(request: Request): Promise<ConnectorConfigurationActionInput> {
  const formData = await request.formData();
  const connectorId = String(formData.get('connectorId') ?? '');
  const secretFields = getSecretFields(formData);
  return {
    connectorId,
    configuration: createConfigurationBody(formData, secretFields),
    values: createFailureValues(formData, secretFields)
  };
}
