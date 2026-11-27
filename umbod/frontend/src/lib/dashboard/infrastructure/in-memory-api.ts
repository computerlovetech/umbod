import type { CataloguePort, DashboardApi } from '../api';
import { userCatalogueSchema, type UserCatalogue } from '../domain/schemas';

export class InMemoryDashboardApi implements DashboardApi {
  readonly catalogue: CataloguePort;

  constructor(catalogue: UserCatalogue) {
    const validated = userCatalogueSchema.parse(catalogue);
    this.catalogue = {
      list: async (): Promise<UserCatalogue> => userCatalogueSchema.parse(validated)
    };
  }
}
