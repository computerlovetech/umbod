import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import { IdentityDirectoryGroupsRoute, IdentityObservationsRoute } from './http-route';

export class IdentityDirectoryApi {
  readonly observations: IdentityObservationsRoute;
  readonly groups: IdentityDirectoryGroupsRoute;
  constructor(transport: Transport) {
    this.observations = new IdentityObservationsRoute(transport);
    this.groups = new IdentityDirectoryGroupsRoute(transport);
  }
}
export function identityDirectoryApi(): IdentityDirectoryApi {
  return new IdentityDirectoryApi(browserTransport());
}
