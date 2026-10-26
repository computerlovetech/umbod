import { catalogueGroupSchema, groupIdSchema, type CatalogueGroup } from './domain/schemas';
import type { GroupCatalogue } from './port';

export class InMemoryGroupCatalogue implements GroupCatalogue {
  private groups: CatalogueGroup[];
  constructor(groups: CatalogueGroup[] = []) {
    this.groups = groups.map((group) => catalogueGroupSchema.parse(group));
  }
  async list(): Promise<CatalogueGroup[]> {
    return this.groups.map((group) => ({ ...group }));
  }
  async register(groupId: string): Promise<void> {
    const group_id = groupIdSchema.parse(groupId);
    if (!this.groups.some((group) => group.group_id === group_id)) this.groups = [...this.groups, { group_id }];
  }
  async delete(groupId: string): Promise<void> {
    groupIdSchema.parse(groupId);
    this.groups = this.groups.filter((group) => group.group_id !== groupId);
  }
}
