import { adminApi } from '#lib/admin/infrastructure/admin-api.js';

import { mapResourceCatalog } from '#lib/admin/capability-catalogs.js';
import { loadUnifiedConnectorInventory } from '#lib/admin/unified-connectors.js';
import { loadSelectedDetail } from '#lib/admin/selected-detail-facade.js';

import type { PageLoad } from './$types';

export const load: PageLoad = async (event) => {
  const admin = adminApi(event.fetch);
  const { mcp, inventory } = await loadUnifiedConnectorInventory(admin);
  const api = admin.downstreamMcpConnectors;
  const connectors = mcp.connectors;
  const detail = await loadSelectedDetail({
    summaries: connectors,
    requestedId: event.url.searchParams.get('connector'),
    idOf: (connector) => connector.connector_id,
    loadDetail: async (id) => {
      const connector = await api.get(id);
      if (connector.authorization_mode === 'personal') return { selectedDetail: connector };
      const bundle = await Promise.all([Promise.resolve(connector), api.tools(id), api.prompts(id), api.resources(id), api.listActivations(id)]);
      const invocationPolicies = bundle[4].tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision }));
      return { selectedDetail: bundle[0], catalog: bundle[1], promptCatalog: bundle[2], resourceCatalog: mapResourceCatalog(bundle[3]), invocationPolicies };
    }
  });
  const selected = 'selectedDetail' in detail ? detail.selectedDetail : undefined;
  return { ...inventory, connectors, selectedConnectorId: detail.selectedId, selectedDetail: selected?.selectedDetail, catalog: selected?.catalog, promptCatalog: selected?.promptCatalog, resourceCatalog: selected?.resourceCatalog, invocationPolicies: selected?.invocationPolicies, selectedDetailFailed: 'selectedDetailFailed' in detail };
};

