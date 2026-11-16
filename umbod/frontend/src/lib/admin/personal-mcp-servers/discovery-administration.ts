import type { EndpointDiscoveryRequest, EndpointDiscoveryResult } from './domain/discovery';

export interface PersonalServerDiscovery {
  discover(request: EndpointDiscoveryRequest): Promise<EndpointDiscoveryResult>;
}
