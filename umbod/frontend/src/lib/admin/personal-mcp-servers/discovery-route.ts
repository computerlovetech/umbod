import { HttpError, type Transport } from '../infrastructure/transport';
import type { PersonalServerDiscovery } from './discovery-administration';
import { EndpointResourceMismatchError, endpointResourceMismatchSchema, endpointDiscoveryRequestSchema, endpointDiscoveryResultForRequest, type EndpointDiscoveryRequest, type EndpointDiscoveryResult } from './domain/discovery';

export class PersonalServerDiscoveryRoute implements PersonalServerDiscovery {
  constructor(private readonly transport: Transport) {}

  async discover(request: EndpointDiscoveryRequest): Promise<EndpointDiscoveryResult> {
    try {
      return await this.transport.request({
        method: 'POST',
        path: '/admin/connectors/mcp/personal-oauth/discovery',
        body: request,
        inputSchema: endpointDiscoveryRequestSchema,
        outputSchema: endpointDiscoveryResultForRequest(request)
      });
    } catch (error) {
      if (error instanceof HttpError && error.status === 422 && endpointResourceMismatchSchema.safeParse(error.body).success) {
        throw new EndpointResourceMismatchError();
      }
      throw error;
    }
  }
}
