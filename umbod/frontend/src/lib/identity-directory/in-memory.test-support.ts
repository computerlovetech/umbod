import { directoryGroupsSchema, directoryQuerySchema, type DirectoryGroups, type DirectoryQuery } from './domain/schemas';
import type { IdentityGroupDirectory, IdentityObservation } from './port';

export class InMemoryIdentityDirectory implements IdentityGroupDirectory, IdentityObservation {
  observations = 0;
  constructor(private readonly directory: DirectoryGroups = { issuer: 'provider', claim: 'groups', groups: [], has_more: false }) {
    directoryGroupsSchema.parse(directory);
  }
  async observe(): Promise<void> { ++this.observations; }
  async list(query: DirectoryQuery): Promise<DirectoryGroups> {
    const input = directoryQuerySchema.parse(query);
    const groups = this.directory.groups.filter((group) => group.value.toLowerCase().includes(input.query.toLowerCase()));
    return directoryGroupsSchema.parse({ ...this.directory, groups: groups.slice(0, input.limit), has_more: groups.length > input.limit });
  }
}
