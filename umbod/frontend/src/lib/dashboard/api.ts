import type { UserCatalogue } from './domain/schemas';
import type { PersonalUsage, UsageDays } from './domain/usage-schemas';

export interface UsagePort {
  get(days: UsageDays, signal?: AbortSignal): Promise<PersonalUsage>;
}

export interface CataloguePort {
  list(signal?: AbortSignal): Promise<UserCatalogue>;
}

export interface DashboardApi {
  readonly catalogue: CataloguePort;
  readonly usage: UsagePort;
}
