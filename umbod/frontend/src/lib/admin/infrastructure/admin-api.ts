import { CapabilityDescriptionsRoute } from '../capability-descriptions-api';
import { ConnectorsApi } from '../connectors-api';
import { DownstreamMcpConnectorsRoute } from '../downstream-mcp-connectors-api';
import { GroupPermissionsApi } from '../group-permissions-api';
import { HttpInstanceConfigurationRoute } from '../instance-configuration-api';
import { OpenApiConnectorsApi } from '../openapi-connectors-api';
import { browserTransport, type Transport } from './transport';
import { currentUserIdentitySchema, type CurrentUserIdentity } from '$lib/header/accountIdentity';


export class AdminApi {
  readonly capabilityDescriptions: CapabilityDescriptionsRoute;
  readonly connectors: ConnectorsApi;
  readonly groupPermissions: GroupPermissionsApi;
  readonly instanceConfiguration: HttpInstanceConfigurationRoute;
  readonly downstreamMcpConnectors: DownstreamMcpConnectorsRoute;
  readonly openApiConnectors: OpenApiConnectorsApi;

  constructor(private readonly transport: Transport) {
    this.capabilityDescriptions = new CapabilityDescriptionsRoute(transport);
    this.connectors = new ConnectorsApi(transport);
    this.groupPermissions = new GroupPermissionsApi(transport);
    this.instanceConfiguration = new HttpInstanceConfigurationRoute(transport);
    this.downstreamMcpConnectors = new DownstreamMcpConnectorsRoute(transport);
    this.openApiConnectors = new OpenApiConnectorsApi(transport);
  }
  currentUser(): Promise<CurrentUserIdentity> {
    return this.transport.request({ method: 'GET', path: '/admin/users', outputSchema: currentUserIdentitySchema });
  }
}

export function adminApi(request: typeof fetch = globalThis.fetch): AdminApi {
  return new AdminApi(browserTransport({ fetch: request }));
}
