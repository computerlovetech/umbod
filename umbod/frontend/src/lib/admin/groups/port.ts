import type { CatalogueGroup } from './domain/schemas';

export interface GroupCatalogue {
  list(): Promise<CatalogueGroup[]>;
  register(groupId: string): Promise<void>;
  delete(groupId: string): Promise<void>;
}
