import { mapResourceCatalog } from '$lib/admin/capability-catalogs';
import { isOperationalError } from '$lib/admin/infrastructure/transport';

import { adminApi } from '$lib/admin/infrastructure/admin-api';

import { mapConnectorApiItem, mapConnectorConfigurationApiResponse, mapConnectorDetailApiResponse } from '$lib/admin/connectors';

import { loadSelectedDetail } from '$lib/admin/selected-detail-facade';

import type { PageLoad } from './$types';

export const load: PageLoad = async (event) => {
  const api = adminApi(event.fetch).connectors;
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

