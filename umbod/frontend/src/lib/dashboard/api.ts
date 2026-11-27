import type { UserCatalogue } from './domain/schemas';

export interface CataloguePort {
  list(signal?: AbortSignal): Promise<UserCatalogue>;
}

export interface DashboardApi {
  readonly catalogue: CataloguePort;
}
