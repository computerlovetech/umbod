import type { Transport } from '../infrastructure/transport';
import type { PersonalServerDiscovery } from './discovery-administration';
import { endpointDiscoveryRequestSchema, endpointDiscoveryResultForRequest, type EndpointDiscoveryRequest, type EndpointDiscoveryResult } from './domain/discovery';

export class PersonalServerDiscoveryRoute implements PersonalServerDiscovery {
  constructor(private readonly transport: Transport) {}

  discover(request: EndpointDiscoveryRequest): Promise<EndpointDiscoveryResult> {
    return this.transport.request({
      method: 'POST',
      path: '/admin/connectors/mcp/personal-oauth/discovery',
      body: request,
      inputSchema: endpointDiscoveryRequestSchema,
      outputSchema: endpointDiscoveryResultForRequest(request)
    });
  }
}
