import { catalogueGroupSchema, createGroupSchema, updateGroupSchema, groupIdSchema, deleteGroupSchema, type CatalogueGroup, type CreateGroup, type UpdateGroup } from './domain/schemas';
import type { GroupCatalogue } from './port';
import { HttpError } from '../infrastructure/transport';

export class InMemoryGroupCatalogue implements GroupCatalogue {
  private groups: CatalogueGroup[];
  constructor(groups: CatalogueGroup[] = []) {
    this.groups = groups.map((group) => catalogueGroupSchema.parse(group));
  }
  async list(): Promise<CatalogueGroup[]> {
    return this.groups.map((group) => ({ ...group }));
  }
  async create(group: CreateGroup): Promise<void> {
    const parsed = createGroupSchema.parse(group);
    if (this.groups.some((entry) => entry.group_id === parsed.group_id)) return;
    this.groups = [...this.groups, { ...parsed, revision: 1 }];
  }
  async update(group: UpdateGroup): Promise<CatalogueGroup> {
    const parsed = updateGroupSchema.parse(group);
    const current = this.groups.find((entry) => entry.group_id === parsed.group_id);
    if (!current) throw new HttpError(404, 'Missing group', null);
    if (current.revision !== parsed.expected_revision) throw new HttpError(409, 'Stale revision', null);
    const updated = catalogueGroupSchema.parse({ group_id: current.group_id, label: parsed.label, description: parsed.description, revision: current.revision + 1 });
    this.groups = this.groups.map((entry) => entry.group_id === updated.group_id ? updated : entry);
    return { ...updated };
  }
  async register(groupId: string): Promise<void> {
    const group_id = groupIdSchema.parse(groupId);
    if (!this.groups.some((group) => group.group_id === group_id)) this.groups = [...this.groups, { group_id, label: group_id, description: '', revision: 1 }];
  }
  async delete(groupId: string): Promise<void> {
    deleteGroupSchema.parse({ group_id: groupId });
    this.groups = this.groups.filter((group) => group.group_id !== groupId);
  }
}
