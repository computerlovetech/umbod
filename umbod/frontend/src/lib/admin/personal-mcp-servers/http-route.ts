import { downstreamMcpConnectorListSchema, downstreamMcpPublicationSchema, type DownstreamMcpConnector, type DownstreamMcpConnectorSummary } from '../downstream-mcp-connectors';
import type { Transport } from '../infrastructure/transport';
import type { PersonalServerAdministration } from './administration';
import { createPersonalServerSchema, personalServerSchema, policySchema, replacePolicySchema, type PersonalPolicy, type PersonalPolicyReplace, type PersonalServerCreate } from './domain/schemas';

export class PersonalServersRoute implements PersonalServerAdministration {
  constructor(private readonly transport: Transport) {}
  private path(id: string): string { return `/admin/connectors/mcp/${encodeURIComponent(id)}`; }
  async list(): Promise<DownstreamMcpConnectorSummary[]> {
    const result = await this.transport.request({ method: 'GET', path: '/admin/connectors/mcp', outputSchema: downstreamMcpConnectorListSchema });
    return result.connectors.filter((server) => server.authorization_mode === 'personal');
  }
  get(id: string): Promise<DownstreamMcpConnector> {
    return this.transport.request({ method: 'GET', path: this.path(id), outputSchema: personalServerSchema.refine((server) => server.connector_id === id) });
  }
  async policy(id: string): Promise<PersonalPolicy> {
    await this.get(id);
    return this.transport.request({ method: 'GET', path: `${this.path(id)}/personal-oauth`, outputSchema: policySchema.refine((policy) => policy.connector_id === id) });
  }
  create(body: PersonalServerCreate): Promise<DownstreamMcpConnector> {
    return this.transport.request({ method: 'POST', path: '/admin/connectors/mcp/personal-oauth', body, inputSchema: createPersonalServerSchema, outputSchema: personalServerSchema.refine((server) => server.publication_status === 'unpublished') });
  }
  async replacePolicy(id: string, body: PersonalPolicyReplace): Promise<PersonalPolicy> {
    replacePolicySchema.parse(body);
    await this.get(id);
    return this.transport.request({ method: 'PUT', path: `${this.path(id)}/personal-oauth`, body, inputSchema: replacePolicySchema, outputSchema: policySchema.refine((policy) => policy.connector_id === id) });
  }
  async publish(id: string): Promise<{ connector_id: string; publication_status: 'published' | 'unpublished' }> {
    await this.get(id);
    return this.transport.request({ method: 'PUT', path: `${this.path(id)}/publication`, outputSchema: downstreamMcpPublicationSchema.refine((result) => result.connector_id === id && result.publication_status === 'published') });
  }
  async withdraw(id: string): Promise<{ connector_id: string; publication_status: 'published' | 'unpublished' }> {
    await this.get(id);
    return this.transport.request({ method: 'DELETE', path: `${this.path(id)}/publication`, outputSchema: downstreamMcpPublicationSchema.refine((result) => result.connector_id === id && result.publication_status === 'unpublished') });
  }
  async delete(id: string): Promise<void> {
    await this.get(id);
    await this.transport.request({ method: 'DELETE', path: this.path(id) });
  }
}
