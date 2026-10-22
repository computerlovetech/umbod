import { adminApi } from '$lib/admin/infrastructure/admin-api';

import { mapResourceCatalog } from '$lib/admin/capability-catalogs';
import { loadSelectedDetail } from '$lib/admin/selected-detail-facade';

import type { PageLoad } from './$types';

export const load: PageLoad = async (event) => {
  const api = adminApi(event.fetch).downstreamMcpConnectors;
  const result = await api.list();
  const connectors = result.connectors.filter((connector) => connector.authorization_mode === 'shared');
  const detail = await loadSelectedDetail({
    summaries: connectors,
    requestedId: event.url.searchParams.get('connector'),
    idOf: (connector) => connector.connector_id,
    loadDetail: async (id) => {
      const connector = await api.get(id);
      if (connector.authorization_mode !== 'shared') throw new Error('Shared connector ownership is required');
      const bundle = await Promise.all([Promise.resolve(connector), api.tools(id), api.prompts(id), api.resources(id), api.listActivations(id)]);
      const invocationPolicies = bundle[4].tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision }));
      return { selectedDetail: bundle[0], catalog: bundle[1], promptCatalog: bundle[2], resourceCatalog: mapResourceCatalog(bundle[3]), invocationPolicies };
    }
  });
  const selected = 'selectedDetail' in detail ? detail.selectedDetail : undefined;
  return { connectors, selectedConnectorId: detail.selectedId, selectedDetail: selected?.selectedDetail, catalog: selected?.catalog, promptCatalog: selected?.promptCatalog, resourceCatalog: selected?.resourceCatalog, invocationPolicies: selected?.invocationPolicies, selectedDetailFailed: 'selectedDetailFailed' in detail };
};

