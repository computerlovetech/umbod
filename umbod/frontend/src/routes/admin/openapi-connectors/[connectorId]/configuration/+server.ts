import { error, json, type RequestHandler } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { openApiConfigurationRequestSchema } from '$lib/admin/openapi-connectors';

export const GET: RequestHandler = async (event) => {
  const connectorId = event.params.connectorId;
  if (connectorId === undefined) error(400, 'Connector ID is required');
  return json(await adminServerApi(event).openApiConnectors.connectors.getConfiguration(connectorId));
};

export const PUT: RequestHandler = async (event) => {
  const connectorId = event.params.connectorId;
  if (connectorId === undefined) error(400, 'Connector ID is required');
  const input = openApiConfigurationRequestSchema.parse(await event.request.json());
  return json(await adminServerApi(event).openApiConnectors.connectors.putConfiguration(connectorId, input));
};
