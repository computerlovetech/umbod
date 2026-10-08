
import { adminApi } from '$lib/admin/infrastructure/admin-api';

import { loadOpenApiConnectorList } from '$lib/admin/openapi-connectors-api';
import { mapOpenApiConnector } from '$lib/admin/openapi-connectors';
import { loadSelectedDetail } from '$lib/admin/selected-detail-facade';

import type { PageLoad } from './$types';

export const load: PageLoad = async (event) => {
  const api = adminApi(event.fetch).openApiConnectors;
  const list = await loadOpenApiConnectorList(api);
  if (list.status !== 'ready') return list;
  const detail = await loadSelectedDetail({
    summaries: list.connectors,
    requestedId: event.url.searchParams.get('connector'),
    idOf: (connector) => connector.id,
    loadDetail: async (id) => {
      const [connector, activation] = await Promise.all([api.connectors.get(id), api.connectors.listActivations(id)]);
      return {
        connector: mapOpenApiConnector(connector),
        invocationPolicies: activation.tools.map((tool) => ({
          tool_id: tool.tool_id,
          mode: tool.invocation_mode,
          revision: tool.policy_revision
        }))
      };
    }
  });
  if (detail.selectedId === undefined) return list;
  return 'selectedDetailFailed' in detail
    ? { ...list, selectedConnectorId: detail.selectedId, selectedDetailFailed: true as const }
    : { ...list, selectedConnectorId: detail.selectedId, selectedDetail: detail.selectedDetail.connector, invocationPolicies: detail.selectedDetail.invocationPolicies };
};
