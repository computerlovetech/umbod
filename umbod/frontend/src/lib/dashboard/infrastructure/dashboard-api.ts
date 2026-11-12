import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { DashboardApi } from '../api';
import { CatalogueRoute } from './catalogue-route';
import { UsageRoute } from './usage-route';

export class HttpDashboardApi implements DashboardApi {
  readonly catalogue: CatalogueRoute;
  readonly usage: UsageRoute;

  constructor(transport: Transport) {
    this.catalogue = new CatalogueRoute(transport);
    this.usage = new UsageRoute(transport);
  }
}

export function browserDashboardApi(): DashboardApi {
  return new HttpDashboardApi(browserTransport());
}
