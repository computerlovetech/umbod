import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary } from '../downstream-mcp-connectors';
import { HttpError } from '../infrastructure/transport';
import type { PersonalServerAdministration } from './administration';
import { createPersonalServerSchema, personalServerSchema, policySchema, replacePolicySchema, type PersonalPolicy, type PersonalPolicyReplace, type PersonalServerCreate, type PersonalSettings } from './domain/schemas';

export function projectClient(client: PersonalSettings['client']): PersonalPolicy['client'] {
  if (client.kind !== 'preconfigured_confidential') return { ...client };
  return { kind: client.kind, issuer_url: client.issuer_url, client_id: client.client_id, token_endpoint_auth_method: client.token_endpoint_auth_method, client_secret_configured: true };
}

export class InMemoryPersonalServers implements PersonalServerAdministration {
  private servers = new Map<string, DownstreamMcpConnector>();
  private policies = new Map<string, PersonalPolicy>();
  constructor(servers: DownstreamMcpConnector[] = [], policies: PersonalPolicy[] = [], private readonly grants: ReadonlySet<string> = new Set()) {
    servers.forEach((server) => this.servers.set(server.connector_id, personalServerSchema.parse(server)));
    policies.forEach((policy) => this.policies.set(policy.connector_id, policySchema.parse(policy)));
  }
  async list(): Promise<DownstreamMcpConnectorSummary[]> {
    return [...this.servers.values()].map(({ connector_id, display_name, icon_url, auth_mode, authorization_mode, publication_status, health }) => ({ connector_id, display_name, icon_url, auth_mode, authorization_mode, publication_status, health }));
  }
  async get(id: string): Promise<DownstreamMcpConnector> {
    const server = this.servers.get(id);
    if (!server) throw new HttpError(404, '', null);
    return structuredClone(server);
  }
  async policy(id: string): Promise<PersonalPolicy> {
    await this.get(id);
    const policy = this.policies.get(id);
    if (!policy) throw new HttpError(404, '', null);
    return structuredClone(policy);
  }
  async create(input: PersonalServerCreate): Promise<DownstreamMcpConnector> {
    const parsed = createPersonalServerSchema.parse(input);
    const id = parsed.metadata.public_path.slice('/mcp/proxies/'.length);
    if (this.servers.has(id)) throw new HttpError(409, '', { detail: { code: 'connector_conflict' } });
    const server = personalServerSchema.parse({ ...parsed.metadata, connector_id: id, icon_url: '', base_capability_description: parsed.metadata.capability_description, effective_capability_description: parsed.metadata.capability_description, capability_description_override: { state: 'system', revision: 0 }, endpoint_url: parsed.configuration.endpoint_url, public_url: `https://umbod.test${parsed.metadata.public_path}`, auth_mode: 'oauth', authorization_mode: 'personal', header_type: 'bearer', custom_header_name: null, credential_configured: false, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null } });
    this.servers.set(id, server);
    this.policies.set(id, { connector_id: id, revision: crypto.randomUUID(), requested_scopes: parsed.configuration.oauth_configuration.requested_scopes, client: projectClient(parsed.configuration.oauth_configuration.client) });
    return structuredClone(server);
  }
  async replacePolicy(id: string, input: PersonalPolicyReplace): Promise<PersonalPolicy> {
    const parsed = replacePolicySchema.parse(input);
    await this.get(id);
    const current = this.policies.get(id);
    if (!current) throw new HttpError(404, '', null);
    if (current.revision !== parsed.expected_revision) throw new HttpError(409, '', { detail: { code: 'personal_oauth_configuration_conflict' } });
    const client = projectClient(parsed.settings.client);
    const unchanged = client.kind !== 'preconfigured_confidential' && JSON.stringify({ requested_scopes: current.requested_scopes, client: current.client }) === JSON.stringify({ requested_scopes: parsed.settings.requested_scopes, client });
    const next = { connector_id: id, revision: unchanged ? current.revision : crypto.randomUUID(), requested_scopes: parsed.settings.requested_scopes, client };
    this.policies.set(id, next);
    return structuredClone(next);
  }
  async publish(id: string): Promise<{ connector_id: string; publication_status: 'published' }> {
    this.servers.set(id, { ...await this.get(id), publication_status: 'published' });
    return { connector_id: id, publication_status: 'published' };
  }
  async withdraw(id: string): Promise<{ connector_id: string; publication_status: 'unpublished' }> {
    this.servers.set(id, { ...await this.get(id), publication_status: 'unpublished' });
    return { connector_id: id, publication_status: 'unpublished' };
  }
  async delete(id: string): Promise<void> {
    await this.get(id);
    if (this.grants.has(id)) throw new HttpError(409, '', { detail: { code: 'downstream_connector_grants_conflict' } });
    this.servers.delete(id);
    this.policies.delete(id);
  }
}
