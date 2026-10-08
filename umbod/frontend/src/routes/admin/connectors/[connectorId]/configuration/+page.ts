
import type { PageLoad } from './$types';
import { loadConnectorConfiguration } from '$lib/admin/connectors-api';
import { adminApi } from '$lib/admin/infrastructure/admin-api';

export const load: PageLoad = (event) => {
  return loadConnectorConfiguration(adminApi(event.fetch).connectors, event.params.connectorId);
};

