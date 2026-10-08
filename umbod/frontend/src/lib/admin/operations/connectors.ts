import { operationFailure, operationRedirect, type BrowserOperations } from './contracts';
import { promptActivationBatchRequestSchema, resourceActivationBatchRequestSchema } from '$lib/admin/capability-catalogs';
import { HttpError, isOperationalError } from '$lib/admin/infrastructure/transport';
import { invocationPolicyBatchUpdateRequestSchema, invocationPolicyConflictResponseSchema } from '$lib/admin/invocation-policy';
import { connectorToolActivationBatchRequestSchema } from '$lib/admin/connectors';
import { checkConnectorConfiguration, publishConnector, saveConnectorConfiguration, unpublishConnector } from '$lib/admin/connectors-api';
import { createConfigurationBody, createFailureValues, getSecretFields } from '$lib/admin/connectors-forms';

import { presentSaveFailureWithReconciliation } from '$lib/admin/tool-activation-reconciliation';

type ConnectorConfigurationActionInput = {
  connectorId: string;
  configuration: Record<string, string>;
  values: Record<string, string>;
};

export const connectorsOperations: BrowserOperations = {
  publish: async (api, data) => publishConnector(api.connectors, String(data.get('connectorId') ?? '')),
  unpublish: async (api, data) => unpublishConnector(api.connectors, String(data.get('connectorId') ?? '')),
  saveToolActivations: async (api, data) => {
    const connectorId = String(data.get('connectorId') ?? '');
    let activations: unknown;
    let policies: unknown;
    try { activations = JSON.parse(String(data.get('toolActivations') ?? '')); policies = JSON.parse(String(data.get('invocationPolicies') ?? '')); } catch { return operationFailure(422, { status: 'invalid', message: 'Tool changes are invalid.' }); }
    const activationTools = Array.isArray(activations) ? activations.map((tool) => typeof tool === 'object' && tool !== null ? { tool_id: String(tool.operationName ?? ''), activation_status: tool.activationStatus } : tool) : [];
    const activationInput = activationTools.length ? connectorToolActivationBatchRequestSchema.safeParse({ tools: activationTools }) : null;
    const policyTools = typeof policies === 'object' && policies !== null && 'tools' in policies && Array.isArray(policies.tools) ? policies.tools : [];
    const policyInput = policyTools.length ? invocationPolicyBatchUpdateRequestSchema.safeParse(policies) : null;
    if (!connectorId || (!activationInput && !policyInput) || (activationInput && !activationInput.success) || (policyInput && !policyInput.success)) return operationFailure(422, { status: 'invalid', message: 'Tool changes are invalid.' });
    try {
      const changes = new Map<string, { toolId: string; activationStatus?: 'enabled' | 'disabled'; invocationMode?: 'direct' | 'ask'; expectedPolicyRevision?: number }>();
      activationInput?.data.tools.forEach((tool) => changes.set(tool.tool_id, { toolId: tool.tool_id, activationStatus: tool.activation_status }));
      policyInput?.data.tools.forEach((tool) => changes.set(tool.tool_id, { ...changes.get(tool.tool_id), toolId: tool.tool_id, invocationMode: tool.mode, expectedPolicyRevision: tool.expected_revision }));
      const response = await api.connectors.tools.saveActivations(connectorId, [...changes.values()]);
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
        loadAuthoritative: () => api.connectors.tools.listActivations(connectorId),
        presentAuthoritative: (authoritativeActivationResponse) => ({
          authoritativeActivationResponse,
          authoritativePolicyResponse: { connector_kind: 'native' as const, connector_id: connectorId, tools: authoritativeActivationResponse.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision })) }
        })
      });
      return operationFailure(presented.status, presented.data);
    }
  },
  savePromptActivations: async (api, data) => {
    const connectorId = String(data.get('connectorId') ?? '');
    let activations: unknown;
    try { activations = JSON.parse(String(data.get('promptActivations') ?? '')); }
    catch { return operationFailure(422, { status: 'invalid', message: 'Prompt changes are invalid.' }); }
    const prompts = Array.isArray(activations)
      ? activations.map((item) => typeof item === 'object' && item !== null
        ? { prompt_id: String((item as { promptId?: unknown }).promptId ?? ''), activation_status: (item as { activationStatus?: unknown }).activationStatus }
        : item)
      : [];
    const parsed = promptActivationBatchRequestSchema.safeParse({ prompts });
    if (!connectorId || !parsed.success) return operationFailure(422, { status: 'invalid', message: 'Prompt changes are invalid.' });
    try {
      await api.connectors.prompts.saveActivations(connectorId, parsed.data);
      return { status: 'saved', connectorId };
    } catch (error) {
      if (!isOperationalError(error)) throw error;
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => ({ status: 503, data: { status: 'failed' as const, connectorId, errorMessage: 'Prompt changes could not be saved.' } }),
        loadAuthoritative: () => api.connectors.prompts.list(connectorId),
        presentAuthoritative: (catalog) => ({
          authoritativePromptResponse: {
            connector_id: connectorId,
            prompts: catalog.prompts.map((prompt) => ({ prompt_id: prompt.name, activation_status: prompt.activation_status }))
          }
        })
      });
      return operationFailure(presented.status, presented.data);
    }
  },
  saveResourceActivations: async (api, data) => {
    const connectorId = String(data.get('connectorId') ?? '');
    let activations: unknown;
    try { activations = JSON.parse(String(data.get('resourceActivations') ?? '')); }
    catch { return operationFailure(422, { status: 'invalid', message: 'Resource changes are invalid.' }); }
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
    if (!connectorId || !parsed.success) return operationFailure(422, { status: 'invalid', message: 'Resource changes are invalid.' });
    try {
      await api.connectors.resources.saveActivations(connectorId, parsed.data);
      return { status: 'saved', connectorId };
    } catch (error) {
      if (!isOperationalError(error)) throw error;
      const presented = await presentSaveFailureWithReconciliation({
        originalError: error,
        presentOriginal: () => ({ status: 503, data: { status: 'failed' as const, connectorId, errorMessage: 'Resource changes could not be saved.' } }),
        loadAuthoritative: () => api.connectors.resources.list(connectorId),
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
      return operationFailure(presented.status, presented.data);
    }
  },
  checkConfiguration: async (api, data) => {
    const { connectorId, configuration, values } = connectorConfigurationActionInput(data);
    const result = await checkConnectorConfiguration(api.connectors, connectorId, configuration);

    if (result.status === 'valid') {
      return { status: 'check-valid', connectorId, successMessage: 'Configuration check passed', values };
    }

    if (result.status === 'invalid') {
      return { status: 'check-invalid', connectorId, errorMessage: result.message, fieldMessages: result.fieldMessages, values };
    }

    return { status: 'failed', connectorId, errorMessage: result.errorMessage, values };
  },
  saveConfigurationAndReturn: async (api, data) => {
    const { connectorId, configuration, values } = connectorConfigurationActionInput(data);
    const result = await saveConnectorConfiguration(api.connectors, connectorId, configuration);
    if (result.status === 'failed') return { status: 'failed', connectorId, errorMessage: result.errorMessage, values };
    return operationRedirect(`/admin/connectors?configured=${encodeURIComponent(connectorId)}`);
  },
  saveConfiguration: async (api, data) => {
    const { connectorId, configuration, values } = connectorConfigurationActionInput(data);
    const result = await saveConnectorConfiguration(api.connectors, connectorId, configuration);

    if (result.status === 'failed') {
      return { status: 'failed', connectorId, errorMessage: result.errorMessage, values };
    }

    return { status: 'saved', connectorId, successMessage: `${connectorId} was configured successfully` };
  }
};

function connectorConfigurationActionInput(formData: FormData): ConnectorConfigurationActionInput {
  const connectorId = String(formData.get('connectorId') ?? '');
  const secretFields = getSecretFields(formData);
  return {
    connectorId,
    configuration: createConfigurationBody(formData, secretFields),
    values: createFailureValues(formData, secretFields)
  };
}
