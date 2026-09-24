import { json } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async (event) => {
  const api = adminServerApi(event).openApiConnectors.connectors;
  const connectorId = event.params.connectorId;
  const [connector, activation] = await Promise.all([
    api.get(connectorId),
    api.listActivations(connectorId)
  ]);
  const invocationPolicies = {
    connector_kind: 'openapi' as const,
    connector_id: connectorId,
    tools: activation.tools.map((tool) => ({
      tool_id: tool.tool_id,
      mode: tool.invocation_mode,
      revision: tool.policy_revision
    }))
  };
  return json({ connector, invocationPolicies });
};
