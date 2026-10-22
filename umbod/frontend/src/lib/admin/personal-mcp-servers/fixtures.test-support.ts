import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary } from '../downstream-mcp-connectors';
import type { PersonalPolicy, PersonalServerCreate } from './domain/schemas';

export function serverFixture(id: string = 'personal'): DownstreamMcpConnector {
  return { connector_id: id, display_name: 'Personal server', tool_name_prefix: 'personal', icon_url: '', capability_description: 'Search records', base_capability_description: 'Search records', effective_capability_description: 'Search records', capability_description_override: { state: 'system', revision: 0 }, endpoint_url: 'https://provider.test/mcp', public_path: `/mcp/proxies/${id}`, public_url: `https://umbod.test/mcp/proxies/${id}`, auth_mode: 'oauth', authorization_mode: 'personal', header_type: 'bearer', custom_header_name: null, credential_configured: false, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null } };
}
export function summaryFixture(id: string = 'personal'): DownstreamMcpConnectorSummary {
  const { connector_id, display_name, icon_url, auth_mode, authorization_mode, publication_status, health } = serverFixture(id);
  return { connector_id, display_name, icon_url, auth_mode, authorization_mode, publication_status, health };
}
export function policyFixture(id: string = 'personal'): PersonalPolicy {
  return { connector_id: id, revision: 'r1', requested_scopes: [], client: { kind: 'dynamic_public' } };
}
export function createFixture(): PersonalServerCreate {
  return { metadata: { display_name: 'Personal server', tool_name_prefix: 'personal', capability_description: 'Search records', public_path: '/mcp/proxies/personal' }, configuration: { endpoint_url: 'https://provider.test/mcp', oauth_configuration: { requested_scopes: [], client: { kind: 'dynamic_public' } } } };
}
