import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { DashboardApi } from '../api';
import { CatalogueRoute } from './catalogue-route';

export class HttpDashboardApi implements DashboardApi {
  readonly catalogue: CatalogueRoute;

  constructor(transport: Transport) {
    this.catalogue = new CatalogueRoute(transport);
  }
}

export function browserDashboardApi(): DashboardApi {
  return new HttpDashboardApi(browserTransport());
}
