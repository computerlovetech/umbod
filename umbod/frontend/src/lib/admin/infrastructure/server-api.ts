import type { RequestEvent } from '@sveltejs/kit';
import { CapabilityDescriptionsRoute } from '../capability-descriptions-api';
import { ConnectorsApi } from '../connectors-api';
import { DownstreamMcpConnectorsRoute } from '../downstream-mcp-connectors-api';
import { GroupPermissionsApi } from '../group-permissions-api';
import { HttpInstanceConfigurationRoute } from '../instance-configuration-api';
import { OpenApiConnectorsApi } from '../openapi-connectors-api';
import { serverTransport } from './transport';

type ServerApiEvent = Pick<RequestEvent, 'fetch' | 'request'>;

export class AdminServerApi {
  readonly capabilityDescriptions: CapabilityDescriptionsRoute;
  readonly connectors: ConnectorsApi;
  readonly groupPermissions: GroupPermissionsApi;
  readonly instanceConfiguration: HttpInstanceConfigurationRoute;
  readonly downstreamMcpConnectors: DownstreamMcpConnectorsRoute;
  readonly openApiConnectors: OpenApiConnectorsApi;

  constructor(event: ServerApiEvent) {
    const transport = serverTransport(event.fetch, event.request);
    this.capabilityDescriptions = new CapabilityDescriptionsRoute(transport);
    this.connectors = new ConnectorsApi(transport);
    this.groupPermissions = new GroupPermissionsApi(transport);
    this.instanceConfiguration = new HttpInstanceConfigurationRoute(transport);
    this.downstreamMcpConnectors = new DownstreamMcpConnectorsRoute(transport);
    this.openApiConnectors = new OpenApiConnectorsApi(transport);
  }
}

export function adminServerApi(event: ServerApiEvent): AdminServerApi {
  return new AdminServerApi(event);
}
