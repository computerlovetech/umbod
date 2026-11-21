import { redirect } from '@sveltejs/kit';
import { mapResourceCatalog } from '#lib/admin/capability-catalogs.js';
import { isOperationalError } from '#lib/admin/infrastructure/transport.js';

import { adminApi } from '#lib/admin/infrastructure/admin-api.js';

import { mapConnectorConfigurationApiResponse, mapConnectorDetailApiResponse } from '#lib/admin/connectors.js';

import { connectorWorkspaceHref, loadUnifiedConnectorInventory } from '#lib/admin/unified-connectors.js';
import { loadSelectedDetail } from '#lib/admin/selected-detail-facade.js';

import type { PageLoad } from './$types';

export const load: PageLoad = async (event) => {
  const admin = adminApi(event.fetch);
  const { native, inventory } = await loadUnifiedConnectorInventory(admin);
  const api = admin.connectors;
  const allConnectors = native.connectors;
  const requestedId = event.url.searchParams.get('connector');
  const requestedConnector = allConnectors.find((connector) => connector.id === requestedId);
  const first = inventory.unifiedRows[0];
  if (!requestedConnector && first && first.kind !== 'native' && event.url.searchParams.get('setup') !== 'native') {
    redirect(307, connectorWorkspaceHref(first, event.url.searchParams.get('capability')));
  }
  if (native.status === 'failed') return { ...inventory, status: 'failed' as const, connectors: [] };
  if (requestedConnector && !requestedConnector.isConfigured) {
    try {
      const configuration = mapConnectorConfigurationApiResponse(await api.connectors.getConfiguration(requestedConnector.id));
      const connectors = allConnectors.map((connector) => connector.id === requestedConnector.id
        ? { ...connector, configurationFields: configuration.fields }
        : connector);
      return { ...inventory, status: 'ready' as const, connectors, selectedConnectorId: requestedConnector.id };
    } catch (error) {
      if (!isOperationalError(error)) throw error;
      return { ...inventory, status: 'ready' as const, connectors: allConnectors, selectedConnectorId: requestedConnector.id, selectedDetailFailed: true as const };
    }
  }
  const selected = await loadSelectedDetail({
    summaries: allConnectors,
    requestedId: requestedConnector?.id ?? (first?.kind === 'native' ? first.id : null),
    idOf: (connector) => connector.id,
    loadDetail: async (id) => {
      const [detail, activation, configuration, prompts, resources] = await Promise.all([api.connectors.get(id), api.tools.listActivations(id), api.connectors.getConfiguration(id), api.prompts.list(id), api.resources.list(id)]);
      const invocationPolicies = activation.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision }));
      return { detail: mapConnectorDetailApiResponse(detail, activation), configuration: mapConnectorConfigurationApiResponse(configuration), promptCatalog: prompts, resourceCatalog: mapResourceCatalog(resources), invocationPolicies };
    },
    eligible: (connector) => connector.isConfigured
  });
  if (selected.selectedId === undefined) return { ...inventory, status: 'ready' as const, connectors: allConnectors };
  if ('selectedDetailFailed' in selected) return { ...inventory, status: 'ready' as const, connectors: allConnectors, selectedConnectorId: selected.selectedId, selectedDetailFailed: true as const };
  const connectors = allConnectors.map((connector) => connector.id === selected.selectedId
    ? { ...connector, tools: selected.selectedDetail.detail.status === 'ready' ? selected.selectedDetail.detail.tools : [], configurationFields: selected.selectedDetail.configuration.status === 'ready' ? selected.selectedDetail.configuration.fields : undefined }
    : connector);
  return { ...inventory, status: 'ready' as const, connectors, selectedConnectorId: selected.selectedId, selectedDetail: selected.selectedDetail.detail, selectedPromptCatalog: selected.selectedDetail.promptCatalog, selectedResourceCatalog: selected.selectedDetail.resourceCatalog, invocationPolicies: selected.selectedDetail.invocationPolicies };
};
