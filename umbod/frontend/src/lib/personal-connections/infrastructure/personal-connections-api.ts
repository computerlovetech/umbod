import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { PersonalConnectionsApi } from '../api';
import { ConnectionsRoute } from './connections-route';
import { AuthorizationRoute } from './authorization-route';

export class HttpPersonalConnectionsApi implements PersonalConnectionsApi {
  readonly connections: ConnectionsRoute;
  readonly authorization: AuthorizationRoute;

  constructor(transport: Transport) {
    this.connections = new ConnectionsRoute(transport);
    this.authorization = new AuthorizationRoute(transport);
  }
}

export function browserPersonalConnectionsApi(): PersonalConnectionsApi {
  return new HttpPersonalConnectionsApi(browserTransport());
}
