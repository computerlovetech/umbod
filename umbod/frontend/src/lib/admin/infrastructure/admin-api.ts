import { OverviewRoute } from '../overview/http-route';
import { GroupsRoute } from '../groups/http-route';
import { FilesystemRoute } from '../filesystem/http-route';
import { PersonalServersRoute } from '../personal-mcp-servers/http-route';
import { CapabilityDescriptionsRoute } from '../capability-descriptions-api';
import { ConnectorsApi } from '../connectors-api';
import { DownstreamMcpConnectorsRoute } from '../downstream-mcp-connectors-api';
import { GroupPermissionsApi } from '../group-permissions-api';
import { HttpInstanceConfigurationRoute } from '../instance-configuration-api';
import { OpenApiConnectorsApi } from '../openapi-connectors-api';
import { browserTransport, type Transport } from './transport';
import { currentUserIdentitySchema, type CurrentUserIdentity } from '$lib/header/accountIdentity';


export class AdminApi {
  readonly overview: OverviewRoute;
  readonly groups: GroupsRoute;
  readonly filesystem: FilesystemRoute;
  readonly personalServers: PersonalServersRoute;
  readonly capabilityDescriptions: CapabilityDescriptionsRoute;
  readonly connectors: ConnectorsApi;
  readonly groupPermissions: GroupPermissionsApi;
  readonly instanceConfiguration: HttpInstanceConfigurationRoute;
  readonly downstreamMcpConnectors: DownstreamMcpConnectorsRoute;
  readonly openApiConnectors: OpenApiConnectorsApi;

  constructor(private readonly transport: Transport) {
    this.overview = new OverviewRoute(transport);
    this.groups = new GroupsRoute(transport);
    this.filesystem = new FilesystemRoute(transport);
    this.personalServers = new PersonalServersRoute(transport);
    this.capabilityDescriptions = new CapabilityDescriptionsRoute(transport);
    this.connectors = new ConnectorsApi(transport);
    this.groupPermissions = new GroupPermissionsApi(transport, this.groups);
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
