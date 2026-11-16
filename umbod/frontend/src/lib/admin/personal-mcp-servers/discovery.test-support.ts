import type { PersonalServerDiscovery } from './discovery-administration';
import { endpointDiscoveryRequestSchema, endpointDiscoveryResultForRequest, endpointDiscoveryResultSchema, type EndpointDiscoveryRequest, type EndpointDiscoveryResult } from './domain/discovery';

export class InMemoryPersonalServerDiscovery implements PersonalServerDiscovery {
  readonly requests: EndpointDiscoveryRequest[] = [];
  private readonly results: EndpointDiscoveryResult[];

  constructor(results: EndpointDiscoveryResult[] = []) {
    this.results = results.map((result): EndpointDiscoveryResult => endpointDiscoveryResultSchema.parse(result));
  }

  async discover(request: EndpointDiscoveryRequest): Promise<EndpointDiscoveryResult> {
    const parsed = endpointDiscoveryRequestSchema.parse(request);
    this.requests.push(parsed);
    const result = this.results.shift();
    if (result === undefined) throw new Error('No endpoint discovery result queued');
    return endpointDiscoveryResultForRequest(parsed).parse(result);
  }
}
