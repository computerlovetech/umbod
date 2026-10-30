import type { CatalogueGroup, CreateGroup, UpdateGroup } from './domain/schemas';

export interface GroupCatalogue {
  list(): Promise<CatalogueGroup[]>;
  create(group: CreateGroup): Promise<void>;
  update(group: UpdateGroup): Promise<CatalogueGroup>;
  register(groupId: string): Promise<void>;
  delete(groupId: string): Promise<void>;
}
