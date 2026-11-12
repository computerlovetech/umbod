import type { CataloguePort, DashboardApi, UsagePort } from '../api';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { userCatalogueSchema, type UserCatalogue } from '../domain/schemas';

export class InMemoryDashboardApi implements DashboardApi {
  readonly catalogue: CataloguePort;
  readonly usage: UsagePort = {
    get: async (): Promise<never> => { throw new HttpError(503, 'Usage unavailable', null); }
  };

  constructor(catalogue: UserCatalogue) {
    const validated = userCatalogueSchema.parse(catalogue);
    this.catalogue = {
      list: async (): Promise<UserCatalogue> => userCatalogueSchema.parse(validated)
    };
  }
}
