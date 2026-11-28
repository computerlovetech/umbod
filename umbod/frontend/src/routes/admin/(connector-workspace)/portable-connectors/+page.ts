import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
import { isPortableRow, loadUnifiedConnectorInventory } from '#lib/admin/unified-connectors.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, url }) => {
  const { inventory } = await loadUnifiedConnectorInventory(adminApi(fetch));
  const connectors = inventory.unifiedRows.filter(isPortableRow);
  const requestedId = url.searchParams.get('connector');
  const selected = requestedId === null ? connectors[0] : connectors.find((connector) => connector.id === requestedId);
  return { ...inventory, connectors, selected };
};
