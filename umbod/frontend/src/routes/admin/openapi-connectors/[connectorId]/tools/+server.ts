import { error, json, type RequestHandler } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';

export const GET: RequestHandler = async (event) => {
  const connectorId = event.params.connectorId;
  if (connectorId === undefined) error(400, 'Connector ID is required');
  const result = await adminServerApi(event).openApiConnectors.connectors.listTools(connectorId);
  return json(result);
};
