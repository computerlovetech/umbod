import { json } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async (event) => {
  const api = adminServerApi(event).connectors;
  const connectorId = event.params.connectorId;
  const [connector, activation, configuration, prompts, resources] = await Promise.all([
    api.connectors.get(connectorId),
    api.tools.listActivations(connectorId),
    api.connectors.getConfiguration(connectorId),
    api.prompts.list(connectorId),
    api.resources.list(connectorId)
  ]);
  const invocationPolicies = {
    connector_kind: 'native' as const,
    connector_id: connectorId,
    tools: activation.tools.map((tool) => ({ tool_id: tool.tool_id, mode: tool.invocation_mode, revision: tool.policy_revision }))
  };
  return json({ connector, activation, configuration, prompts, resources, invocationPolicies });
};
