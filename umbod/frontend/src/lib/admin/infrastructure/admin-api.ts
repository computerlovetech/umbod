import { NamespacesRoute } from '../filesystem/namespaces-route';
import { AnalyticsRoute } from '../analytics/http-route';
import { GroupsRoute } from '../groups/http-route';
import { PersonalServersRoute } from '../personal-mcp-servers/http-route';
import { PersonalServerDiscoveryRoute } from '../personal-mcp-servers/discovery-route';
import { PersonalOAuthSetupRoute } from '../personal-mcp-servers/setup-route';
import { CapabilityDescriptionsRoute } from '../capability-descriptions-api';
import { ConnectorsApi } from '../connectors-api';
import { DownstreamMcpConnectorsRoute } from '../downstream-mcp-connectors-api';
import { GroupPermissionsApi } from '../group-permissions-api';
import { HttpInstanceConfigurationRoute } from '../instance-configuration-api';
import { OpenApiConnectorsApi } from '../openapi-connectors-api';
import { browserTransport, type Transport } from './transport';


export class AdminApi {
  readonly namespaces: NamespacesRoute;
  readonly analytics: AnalyticsRoute;
  readonly groups: GroupsRoute;
  readonly personalServers: PersonalServersRoute;
  readonly personalServerDiscovery: PersonalServerDiscoveryRoute;
  readonly personalOAuthSetup: PersonalOAuthSetupRoute;
  readonly capabilityDescriptions: CapabilityDescriptionsRoute;
  readonly connectors: ConnectorsApi;
  readonly groupPermissions: GroupPermissionsApi;
  readonly instanceConfiguration: HttpInstanceConfigurationRoute;
  readonly downstreamMcpConnectors: DownstreamMcpConnectorsRoute;
  readonly openApiConnectors: OpenApiConnectorsApi;

  constructor(transport: Transport) {
    this.namespaces = new NamespacesRoute(transport);
    this.analytics = new AnalyticsRoute(transport);
    this.groups = new GroupsRoute(transport);
    this.personalServers = new PersonalServersRoute(transport);
    this.personalServerDiscovery = new PersonalServerDiscoveryRoute(transport);
    this.personalOAuthSetup = new PersonalOAuthSetupRoute(transport);
    this.capabilityDescriptions = new CapabilityDescriptionsRoute(transport);
    this.connectors = new ConnectorsApi(transport);
    this.groupPermissions = new GroupPermissionsApi(transport, this.groups);
    this.instanceConfiguration = new HttpInstanceConfigurationRoute(transport);
    this.downstreamMcpConnectors = new DownstreamMcpConnectorsRoute(transport);
    this.openApiConnectors = new OpenApiConnectorsApi(transport);
  }
}

export function adminApi(request: typeof fetch = globalThis.fetch): AdminApi {
  return new AdminApi(browserTransport({ fetch: request }));
}
